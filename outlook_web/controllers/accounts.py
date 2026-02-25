from __future__ import annotations

import html
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from flask import Response, g, jsonify, request

from outlook_web import config
from outlook_web.audit import log_audit
from outlook_web.db import get_db
from outlook_web.errors import build_error_payload
from outlook_web.repositories import accounts as accounts_repo
from outlook_web.repositories import groups as groups_repo
from outlook_web.repositories import tags as tags_repo
from outlook_web.repositories import refresh_logs as refresh_logs_repo
from outlook_web.repositories import settings as settings_repo
from outlook_web.repositories.refresh_runs import create_refresh_run, finish_refresh_run
from outlook_web.repositories.distributed_locks import acquire_distributed_lock, release_distributed_lock
from outlook_web.security.auth import get_client_ip, get_user_agent, login_required
from outlook_web.security.crypto import decrypt_data
from outlook_web.services import graph as graph_service
from outlook_web.services import refresh as refresh_service


def sanitize_input(text: str, max_length: int = 500) -> str:
    """
    净化用户输入，防止XSS攻击
    - 转义HTML特殊字符
    - 限制长度
    - 移除控制字符
    """
    if not text:
        return ""

    # 限制长度
    text = text[:max_length]

    # 移除控制字符（保留换行和制表符）
    text = ''.join(char for char in text if char.isprintable() or char in '\n\t')

    # 转义HTML特殊字符
    text = html.escape(text, quote=True)

    return text


# ==================== 账号基础 CRUD API ====================


@login_required
def api_get_accounts() -> Any:
    """获取所有账号"""
    group_id = request.args.get('group_id', type=int)
    accounts = accounts_repo.load_accounts(group_id)

    # 获取每个账号的最后刷新状态（批量查询，避免 N+1）
    db = get_db()
    last_log_by_account: Dict[int, Dict[str, Any]] = {}
    try:
        account_ids = [int(a.get('id')) for a in accounts if a.get('id') is not None]
    except Exception:
        account_ids = []

    if account_ids:
        try:
            placeholders = ",".join(["?"] * len(account_ids))
            rows = db.execute(f'''
                SELECT l.account_id, l.status, l.error_message, l.created_at
                FROM account_refresh_logs l
                JOIN (
                    SELECT account_id, MAX(id) as max_id
                    FROM account_refresh_logs
                    WHERE account_id IN ({placeholders})
                    GROUP BY account_id
                ) latest
                ON l.account_id = latest.account_id AND l.id = latest.max_id
            ''', account_ids).fetchall()
            for r in rows:
                try:
                    last_log_by_account[int(r['account_id'])] = dict(r)
                except Exception:
                    continue
        except Exception:
            last_log_by_account = {}

    # 返回时隐藏敏感信息
    safe_accounts = []
    for acc in accounts:
        acc_id = acc.get('id')
        try:
            acc_id_int = int(acc_id)
        except Exception:
            acc_id_int = None
        last_refresh_log = last_log_by_account.get(acc_id_int) if acc_id_int is not None else None

        safe_accounts.append({
            'id': acc['id'],
            'email': acc['email'],
            'client_id': acc['client_id'][:8] + '...' if len(acc['client_id']) > 8 else acc['client_id'],
            'group_id': acc.get('group_id'),
            'group_name': acc.get('group_name', '默认分组'),
            'group_color': acc.get('group_color', '#666666'),
            'remark': acc.get('remark', ''),
            'status': acc.get('status', 'active'),
            'last_refresh_at': acc.get('last_refresh_at', ''),
            'last_refresh_status': last_refresh_log.get('status') if last_refresh_log else None,
            'last_refresh_error': last_refresh_log.get('error_message') if last_refresh_log else None,
            'created_at': acc.get('created_at', ''),
            'updated_at': acc.get('updated_at', ''),
            'tags': acc.get('tags', [])
        })
    return jsonify({'success': True, 'accounts': safe_accounts})


@login_required
def api_get_account(account_id: int) -> Any:
    """获取单个账号详情"""
    account = accounts_repo.get_account_by_id(account_id)
    if not account:
        return jsonify({'success': False, 'error': '账号不存在'})

    return jsonify({
        'success': True,
        'account': {
            'id': account['id'],
            'email': account['email'],
            # 敏感字段默认不回显（避免泄露）；如需查看请走"导出+二次验证"
            'password': '',
            'client_id': account['client_id'],
            'refresh_token': '',
            'has_password': bool(account.get('password')),
            'has_refresh_token': bool(account.get('refresh_token')),
            'group_id': account.get('group_id'),
            'group_name': account.get('group_name', '默认分组'),
            'remark': account.get('remark', ''),
            'status': account.get('status', 'active'),
            'created_at': account.get('created_at', ''),
            'updated_at': account.get('updated_at', '')
        }
    })


@login_required
def api_add_account() -> Any:
    """添加账号"""
    data = request.json
    account_str = data.get('account_string', '')
    group_id = data.get('group_id', 1)

    if not account_str:
        return jsonify({'success': False, 'error': '请输入账号信息'})

    # 校验分组
    target_group = groups_repo.get_group_by_id(group_id)
    if not target_group:
        return jsonify({'success': False, 'error': '分组不存在'})
    if target_group.get('is_system'):
        return jsonify({'success': False, 'error': '不能导入到系统分组'})

    def sanitize_credential_field(value: Any, max_length: int) -> str:
        if value is None:
            return ''
        text = str(value)
        text = text.replace('\r', '').replace('\n', '').replace('\t', '')
        text = text.strip()
        if len(text) > max_length:
            text = text[:max_length]
        # 移除不可见控制字符
        text = ''.join(ch for ch in text if ch.isprintable())
        return text

    def parse_account_string(line: str) -> Optional[Dict[str, str]]:
        """解析账号字符串（格式：email----password----client_id----refresh_token）"""
        parts = line.strip().split('----')
        if len(parts) >= 4:
            return {
                'email': parts[0].strip(),
                'password': parts[1],
                'client_id': parts[2].strip(),
                # refresh_token 可能包含 '----'，这里把剩余部分合并回去
                'refresh_token': '----'.join(parts[3:]).strip()
            }
        return None

    # 支持批量导入（多行）+ 逐行校验与错误定位
    raw_lines = account_str.splitlines()
    imported = 0
    failed = 0
    errors: List[Dict[str, Any]] = []
    errors_total = 0
    max_error_details = 50

    db = get_db()
    for line_no, raw in enumerate(raw_lines, start=1):
        line = (raw or '').strip()
        if not line:
            continue

        parsed = parse_account_string(line)
        if not parsed:
            failed += 1
            errors_total += 1
            if len(errors) < max_error_details:
                errors.append({'line': line_no, 'error': '格式错误，应为：邮箱----密码----client_id----refresh_token'})
            continue

        email_addr = sanitize_credential_field(parsed.get('email'), 320)
        password = sanitize_credential_field(parsed.get('password'), 500)
        client_id = sanitize_credential_field(parsed.get('client_id'), 200)
        refresh_token = sanitize_credential_field(parsed.get('refresh_token'), 4096)

        if not email_addr or not client_id or not refresh_token:
            failed += 1
            errors_total += 1
            if len(errors) < max_error_details:
                errors.append({'line': line_no, 'email': email_addr, 'error': '邮箱、Client ID、Refresh Token 不能为空'})
            continue

        # 基础邮箱格式校验
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email_addr):
            failed += 1
            errors_total += 1
            if len(errors) < max_error_details:
                errors.append({'line': line_no, 'email': email_addr, 'error': '邮箱格式不正确'})
            continue

        ok = accounts_repo.add_account(email_addr, password, client_id, refresh_token, group_id, db=db, commit=False)
        if ok:
            imported += 1
            continue

        failed += 1
        errors_total += 1
        reason = '写入失败'
        try:
            exists = db.execute('SELECT 1 FROM accounts WHERE email = ? LIMIT 1', (email_addr,)).fetchone()
            if exists:
                reason = '邮箱已存在'
        except Exception:
            pass
        if len(errors) < max_error_details:
            errors.append({'line': line_no, 'email': email_addr, 'error': reason})

    summary = {
        'group_id': group_id,
        'total_lines': len(raw_lines),
        'imported': imported,
        'failed': failed,
        'errors_total': errors_total,
        'errors_returned': len(errors),
        'errors_truncated': errors_total > len(errors)
    }

    message = f'导入完成：成功 {imported} 个，失败 {failed} 个'

    if imported > 0:
        try:
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            return jsonify({'success': False, 'error': '数据库写入失败，请重试'})
        log_audit('import', 'account', None, f"{message}，目标分组ID={group_id}")
        return jsonify({'success': True, 'message': message, 'summary': summary, 'errors': errors})

    return jsonify({'success': False, 'error': message, 'summary': summary, 'errors': errors})


@login_required
def api_update_account(account_id: int) -> Any:
    """更新账号"""
    data = request.json

    # 检查是否只更新状态
    if 'status' in data and len(data) == 1:
        # 只更新状态
        return _api_update_account_status(account_id, data['status'])

    email_addr = (data.get('email') or '').strip()
    password = data.get('password')
    client_id = data.get('client_id')
    refresh_token = data.get('refresh_token')
    try:
        group_id = int(data.get('group_id', 1) or 1)
    except Exception:
        group_id = 1
    remark = sanitize_input(data.get('remark', ''), max_length=200)
    status = data.get('status', 'active')

    if not email_addr:
        return jsonify({'success': False, 'error': '邮箱不能为空'})

    target_group = groups_repo.get_group_by_id(group_id)
    if not target_group:
        error_payload = build_error_payload(
            code="GROUP_NOT_FOUND",
            message="分组不存在",
            err_type="NotFoundError",
            status=404,
            details=f"group_id={group_id}",
        )
        return jsonify({'success': False, 'error': error_payload}), 404

    if target_group.get('is_system'):
        error_payload = build_error_payload(
            code="SYSTEM_GROUP_PROTECTED",
            message="不能移动到系统分组",
            err_type="ForbiddenError",
            status=403,
            details=f"group_id={group_id}",
        )
        return jsonify({'success': False, 'error': error_payload}), 403

    if accounts_repo.update_account(account_id, email_addr, password, client_id, refresh_token, group_id, remark, status):
        changed_fields = []
        if isinstance(client_id, str) and client_id.strip():
            changed_fields.append('client_id')
        if isinstance(password, str) and password.strip():
            changed_fields.append('password')
        if isinstance(refresh_token, str) and refresh_token.strip():
            changed_fields.append('refresh_token')
        details = json.dumps({
            "email": email_addr,
            "group_id": group_id,
            "status": status,
            "changed_fields": changed_fields
        }, ensure_ascii=False)
        log_audit('update', 'account', str(account_id), details)
        return jsonify({'success': True, 'message': '账号更新成功'})
    else:
        return jsonify({'success': False, 'error': '更新失败'})


def _api_update_account_status(account_id: int, status: str) -> Any:
    """只更新账号状态"""
    db = get_db()
    try:
        db.execute('''
            UPDATE accounts
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (status, account_id))
        db.commit()
        return jsonify({'success': True, 'message': '状态更新成功'})
    except Exception:
        return jsonify({'success': False, 'error': '更新失败'})


@login_required
def api_delete_account(account_id: int) -> Any:
    """删除账号"""
    email_addr = ''
    try:
        db = get_db()
        row = db.execute('SELECT email FROM accounts WHERE id = ?', (account_id,)).fetchone()
        email_addr = row['email'] if row else ''
    except Exception:
        email_addr = ''
    if accounts_repo.delete_account_by_id(account_id):
        log_audit('delete', 'account', str(account_id), f"删除账号：{email_addr}" if email_addr else "删除账号")
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': '删除失败'})


@login_required
def api_delete_account_by_email(email_addr: str) -> Any:
    """根据邮箱地址删除账号"""
    if accounts_repo.delete_account_by_email(email_addr):
        log_audit('delete', 'account', email_addr, f"删除账号：{email_addr}")
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': '删除失败'})


@login_required
def api_batch_delete_accounts() -> Any:
    """
    批量删除账号 API

    功能：支持一次性删除多个账号，记录审计日志
    """
    data = request.get_json()
    account_ids = data.get('account_ids', [])

    if not account_ids:
        return jsonify({'success': False, 'error': '请选择要删除的账号'})

    if not isinstance(account_ids, list):
        return jsonify({'success': False, 'error': '参数格式错误'})

    deleted_count = 0
    failed_count = 0

    for account_id in account_ids:
        try:
            # 获取邮箱地址用于审计日志
            db = get_db()
            row = db.execute('SELECT email FROM accounts WHERE id = ?', (account_id,)).fetchone()
            email_addr = row['email'] if row else ''

            if accounts_repo.delete_account_by_id(account_id):
                log_audit('delete', 'account', str(account_id), f"批量删除账号：{email_addr}" if email_addr else "批量删除账号")
                deleted_count += 1
            else:
                failed_count += 1
        except Exception:
            failed_count += 1

    return jsonify({
        'success': True,
        'message': f'成功删除 {deleted_count} 个账号' + (f'，失败 {failed_count} 个' if failed_count > 0 else ''),
        'deleted_count': deleted_count,
        'failed_count': failed_count
    })


# ==================== 批量操作 API ====================


@login_required
def api_batch_manage_tags() -> Any:
    """批量管理账号标签"""
    data = request.json
    account_ids: List[int] = data.get('account_ids', [])
    tag_id = data.get('tag_id')
    action = data.get('action')  # add, remove

    if not account_ids or not tag_id or not action:
        return jsonify({'success': False, 'error': '参数不完整'})

    count = 0
    for acc_id in account_ids:
        if action == 'add':
            if tags_repo.add_account_tag(acc_id, tag_id):
                count += 1
        elif action == 'remove':
            if tags_repo.remove_account_tag(acc_id, tag_id):
                count += 1

    try:
        details = json.dumps({'action': action, 'tag_id': tag_id, 'accounts': len(account_ids), 'affected': count}, ensure_ascii=False)
    except Exception:
        details = f"action={action} tag_id={tag_id} accounts={len(account_ids)} affected={count}"
    log_audit('update', 'account_tags', str(tag_id), details)
    return jsonify({'success': True, 'message': f'成功处理 {count} 个账号'})


@login_required
def api_batch_update_account_group() -> Any:
    """批量更新账号分组"""
    data = request.json
    account_ids = data.get('account_ids', [])
    group_id = data.get('group_id')

    if not account_ids:
        return jsonify({'success': False, 'error': '请选择要修改的账号'})

    if not group_id:
        return jsonify({'success': False, 'error': '请选择目标分组'})

    # 验证分组存在
    group = groups_repo.get_group_by_id(group_id)
    if not group:
        return jsonify({'success': False, 'error': '目标分组不存在'})

    # 检查是否是临时邮箱分组（系统保留分组）
    if group.get('is_system'):
        return jsonify({'success': False, 'error': '不能移动到系统分组'})

    # 批量更新
    db = get_db()
    try:
        placeholders = ','.join('?' * len(account_ids))
        db.execute(f'''
            UPDATE accounts SET group_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id IN ({placeholders})
        ''', [group_id] + account_ids)
        db.commit()
        log_audit('update', 'account_group', str(group_id), f"批量移动分组：账号数={len(account_ids)}")
        return jsonify({
            'success': True,
            'message': f'已将 {len(account_ids)} 个账号移动到「{group["name"]}」分组'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@login_required
def api_search_accounts() -> Any:
    """全局搜索账号"""
    query = request.args.get('q', '').strip()

    if not query:
        return jsonify({'success': True, 'accounts': []})

    db = get_db()
    # 支持搜索邮箱、备注和标签
    cursor = db.execute('''
        SELECT DISTINCT a.*, g.name as group_name, g.color as group_color
        FROM accounts a
        LEFT JOIN groups g ON a.group_id = g.id
        LEFT JOIN account_tags at ON a.id = at.account_id
        LEFT JOIN tags t ON at.tag_id = t.id
        WHERE a.email LIKE ? OR a.remark LIKE ? OR t.name LIKE ?
        ORDER BY a.created_at DESC
    ''', (f'%{query}%', f'%{query}%', f'%{query}%'))

    rows = cursor.fetchall()

    # 批量加载标签与最后刷新状态，避免 N+1 查询
    account_rows: List[Dict[str, Any]] = [dict(r) for r in rows]
    try:
        account_ids = [int(a.get('id')) for a in account_rows if a.get('id') is not None]
    except Exception:
        account_ids = []

    tags_by_account: Dict[int, List[Dict[str, Any]]] = {}
    last_log_by_account: Dict[int, Dict[str, Any]] = {}
    if account_ids:
        try:
            placeholders = ",".join(["?"] * len(account_ids))
            tag_rows = db.execute(f'''
                SELECT at.account_id as account_id, t.*
                FROM account_tags at
                JOIN tags t ON t.id = at.tag_id
                WHERE at.account_id IN ({placeholders})
                ORDER BY at.account_id ASC, t.created_at DESC
            ''', account_ids).fetchall()
            for tr in tag_rows:
                tag_dict = dict(tr)
                acc_id = tag_dict.pop('account_id', None)
                if acc_id is None:
                    continue
                tags_by_account.setdefault(int(acc_id), []).append(tag_dict)
        except Exception:
            tags_by_account = {}

        try:
            placeholders = ",".join(["?"] * len(account_ids))
            log_rows = db.execute(f'''
                SELECT l.account_id, l.status, l.error_message, l.created_at
                FROM account_refresh_logs l
                JOIN (
                    SELECT account_id, MAX(id) as max_id
                    FROM account_refresh_logs
                    WHERE account_id IN ({placeholders})
                    GROUP BY account_id
                ) latest
                ON l.account_id = latest.account_id AND l.id = latest.max_id
            ''', account_ids).fetchall()
            for lr in log_rows:
                try:
                    last_log_by_account[int(lr['account_id'])] = dict(lr)
                except Exception:
                    continue
        except Exception:
            last_log_by_account = {}

    safe_accounts = []
    for acc in account_rows:
        acc_id = acc.get('id')
        try:
            acc_id_int = int(acc_id)
        except Exception:
            acc_id_int = None

        tags = tags_by_account.get(acc_id_int, []) if acc_id_int is not None else []
        last_refresh_log = last_log_by_account.get(acc_id_int) if acc_id_int is not None else None

        safe_accounts.append({
            'id': acc['id'],
            'email': acc['email'],
            'client_id': acc['client_id'][:8] + '...' if len(acc['client_id']) > 8 else acc['client_id'],
            'group_id': acc['group_id'],
            'group_name': acc['group_name'] if acc['group_name'] else '默认分组',
            'group_color': acc['group_color'] if acc['group_color'] else '#666666',
            'remark': acc['remark'] if acc['remark'] else '',
            'status': acc['status'] if acc['status'] else 'active',
            'created_at': acc['created_at'] if acc['created_at'] else '',
            'updated_at': acc['updated_at'] if acc['updated_at'] else '',
            'tags': tags,
            'last_refresh_status': last_refresh_log.get('status') if last_refresh_log else None,
            'last_refresh_error': last_refresh_log.get('error_message') if last_refresh_log else None
        })

    return jsonify({'success': True, 'accounts': safe_accounts})


# ==================== 导出功能 API ====================


@login_required
def api_export_all_accounts() -> Any:
    """导出所有邮箱账号为 TXT 文件（需要二次验证）"""
    from outlook_web.security.auth import consume_export_verify_token

    # 检查二次验证token（一次性）
    verify_token = request.args.get('verify_token')
    ok, error_message = consume_export_verify_token(verify_token)
    if not ok:
        return jsonify({'success': False, 'error': error_message, 'need_verify': True}), 401

    # 使用 load_accounts 获取所有账号（自动解密）
    accounts = accounts_repo.load_accounts()

    if not accounts:
        return jsonify({'success': False, 'error': '没有邮箱账号'})

    # 记录审计日志
    log_audit('export', 'all_accounts', None, f"导出所有账号，共 {len(accounts)} 个")

    # 生成导出内容（格式：email----password----client_id----refresh_token）
    lines = []
    for acc in accounts:
        line = f"{acc['email']}----{acc.get('password', '')}----{acc['client_id']}----{acc['refresh_token']}"
        lines.append(line)

    content = '\n'.join(lines)

    # 生成文件名（使用 URL 编码处理中文）
    filename = f"all_accounts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    encoded_filename = quote(filename)

    # 返回文件下载响应
    return Response(
        content,
        mimetype='text/plain; charset=utf-8',
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


@login_required
def api_export_selected_accounts() -> Any:
    """导出选中分组的邮箱账号为 TXT 文件（需要二次验证）"""
    from outlook_web.security.auth import consume_export_verify_token

    data = request.json
    group_ids = data.get('group_ids', [])
    verify_token = data.get('verify_token')

    ok, error_message = consume_export_verify_token(verify_token)
    if not ok:
        return jsonify({'success': False, 'error': error_message, 'need_verify': True}), 401

    if not group_ids:
        return jsonify({'success': False, 'error': '请选择要导出的分组'})

    # 获取选中分组下的所有账号（使用 load_accounts 自动解密）
    all_accounts = []
    for group_id in group_ids:
        accounts = accounts_repo.load_accounts(group_id)
        all_accounts.extend(accounts)

    if not all_accounts:
        return jsonify({'success': False, 'error': '选中的分组下没有邮箱账号'})

    # 记录审计日志
    log_audit('export', 'selected_groups', ','.join(map(str, group_ids)), f"导出选中分组的 {len(all_accounts)} 个账号")

    # 生成导出内容
    lines = []
    for acc in all_accounts:
        line = f"{acc['email']}----{acc.get('password', '')}----{acc['client_id']}----{acc['refresh_token']}"
        lines.append(line)

    content = '\n'.join(lines)

    # 生成文件名
    filename = f"selected_accounts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    encoded_filename = quote(filename)

    # 返回文件下载响应
    return Response(
        content,
        mimetype='text/plain; charset=utf-8',
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


@login_required
def api_generate_export_verify_token() -> Any:
    """���成导出验证token（二次验证）"""
    from outlook_web.security.auth import issue_export_verify_token, get_client_ip, get_user_agent
    from outlook_web.repositories import settings as settings_repo
    from outlook_web.security.crypto import verify_password

    data = request.json
    password = data.get('password', '')

    # 验证密码
    stored_password = settings_repo.get_login_password()
    if not verify_password(password, stored_password):
        return jsonify({'success': False, 'error': '密码错误'})

    # 生成一次性 token
    client_ip = get_client_ip()
    user_agent = get_user_agent()
    verify_token = issue_export_verify_token(client_ip, user_agent)
    return jsonify({'success': True, 'verify_token': verify_token})


# ==================== Token 刷新 API ====================

REFRESH_LOCK_NAME = "refresh_all_tokens"


@login_required
def api_refresh_account(account_id: int) -> Any:
    """刷新单个账号的 token"""
    db = get_db()
    cursor = db.execute('SELECT id, email, client_id, refresh_token, group_id FROM accounts WHERE id = ?', (account_id,))
    account = cursor.fetchone()

    if not account:
        error_payload = build_error_payload(
            "ACCOUNT_NOT_FOUND",
            "账号不存在",
            "NotFoundError",
            404,
            f"account_id={account_id}"
        )
        return jsonify({'success': False, 'error': error_payload})

    account_id = account['id']
    account_email = account['email']
    client_id = account['client_id']
    encrypted_refresh_token = account['refresh_token']

    # 获取分组代理设置
    proxy_url = ''
    if account['group_id']:
        group = groups_repo.get_group_by_id(account['group_id'])
        if group:
            proxy_url = group.get('proxy_url', '') or ''

    # 解密 refresh_token
    try:
        refresh_token = decrypt_data(encrypted_refresh_token) if encrypted_refresh_token else encrypted_refresh_token
    except Exception as e:
        error_msg = f"解密 token 失败: {str(e)}"
        refresh_logs_repo.log_refresh_result(account_id, account_email, 'manual', 'failed', error_msg)
        error_payload = build_error_payload(
            "TOKEN_DECRYPT_FAILED",
            "Token 解密失败",
            "DecryptionError",
            500,
            error_msg
        )
        return jsonify({'success': False, 'error': error_payload})

    # 测试 refresh token
    success, error_msg = graph_service.test_refresh_token(client_id, refresh_token, proxy_url)

    # 记录刷新结果
    refresh_logs_repo.log_refresh_result(account_id, account_email, 'manual', 'success' if success else 'failed', error_msg)

    if success:
        return jsonify({'success': True, 'message': 'Token 刷新成功'})

    error_payload = build_error_payload(
        "TOKEN_REFRESH_FAILED",
        "Token 刷新失败",
        "RefreshTokenError",
        400,
        error_msg or "未知错误"
    )
    return jsonify({'success': False, 'error': error_payload})


@login_required
def api_refresh_all_accounts() -> Any:
    """刷新所有账号的 token（流式响应，实时返回进度）"""
    trace_id_value = None
    try:
        trace_id_value = getattr(g, 'trace_id', None)
    except Exception:
        trace_id_value = None
    requested_by_ip = get_client_ip()
    requested_by_user_agent = get_user_agent()

    def generate():
        yield from refresh_service.stream_refresh_all_accounts(
            trace_id=trace_id_value,
            requested_by_ip=requested_by_ip,
            requested_by_user_agent=requested_by_user_agent,
            lock_name=REFRESH_LOCK_NAME,
            test_refresh_token=graph_service.test_refresh_token,
        )

    return Response(generate(), mimetype='text/event-stream')


@login_required
def api_retry_refresh_account(account_id: int) -> Any:
    """重试单个失败账号的刷新"""
    return api_refresh_account(account_id)


@login_required
def api_refresh_failed_accounts() -> Any:
    """重试所有失败的账号"""
    db = get_db()
    trace_id_value = None
    try:
        trace_id_value = getattr(g, 'trace_id', None)
    except Exception:
        trace_id_value = None
    requested_by_ip = get_client_ip()
    requested_by_user_agent = get_user_agent()

    response_data, status_code = refresh_service.refresh_failed_accounts(
        db=db,
        trace_id=trace_id_value,
        requested_by_ip=requested_by_ip,
        requested_by_user_agent=requested_by_user_agent,
        lock_name=REFRESH_LOCK_NAME,
        test_refresh_token=graph_service.test_refresh_token,
    )
    return jsonify(response_data), status_code


@login_required
def api_trigger_scheduled_refresh() -> Any:
    """手动触发定时刷新（支持强制刷新）"""
    force = request.args.get('force', 'false').lower() == 'true'
    trace_id_value = None
    try:
        trace_id_value = getattr(g, 'trace_id', None)
    except Exception:
        trace_id_value = None
    requested_by_ip = get_client_ip()
    requested_by_user_agent = get_user_agent()

    # 获取配置
    refresh_interval_days = int(settings_repo.get_setting('refresh_interval_days', '30'))
    use_cron = settings_repo.get_setting('use_cron_schedule', 'false').lower() == 'true'

    # 执行刷新（使用流式响应）
    def generate():
        yield from refresh_service.stream_trigger_scheduled_refresh(
            force=force,
            refresh_interval_days=refresh_interval_days,
            use_cron=use_cron,
            trace_id=trace_id_value,
            requested_by_ip=requested_by_ip,
            requested_by_user_agent=requested_by_user_agent,
            lock_name=REFRESH_LOCK_NAME,
            test_refresh_token=graph_service.test_refresh_token,
        )

    return Response(generate(), mimetype='text/event-stream')


# ==================== 刷新日志 API ====================


@login_required
def api_get_refresh_logs() -> Any:
    """获取所有账号的刷新历史（近半年）"""
    db = get_db()
    limit = int(request.args.get('limit', 1000))
    offset = int(request.args.get('offset', 0))

    cursor = db.execute('''
        SELECT l.*, a.email as account_email
        FROM account_refresh_logs l
        LEFT JOIN accounts a ON l.account_id = a.id
        WHERE l.refresh_type IN ('manual', 'manual_all', 'scheduled', 'retry')
        AND l.created_at >= datetime('now', '-6 months')
        ORDER BY l.created_at DESC
        LIMIT ? OFFSET ?
    ''', (limit, offset))

    logs = []
    for row in cursor.fetchall():
        logs.append({
            'id': row['id'],
            'account_id': row['account_id'],
            'account_email': row['account_email'] or row['account_email'],
            'refresh_type': row['refresh_type'],
            'status': row['status'],
            'error_message': row['error_message'],
            'created_at': row['created_at']
        })

    return jsonify({'success': True, 'logs': logs})


@login_required
def api_get_account_refresh_logs(account_id: int) -> Any:
    """获取单个账号的刷新历史"""
    db = get_db()
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))

    cursor = db.execute('''
        SELECT * FROM account_refresh_logs
        WHERE account_id = ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    ''', (account_id, limit, offset))

    logs = []
    for row in cursor.fetchall():
        logs.append({
            'id': row['id'],
            'account_id': row['account_id'],
            'account_email': row['account_email'],
            'refresh_type': row['refresh_type'],
            'status': row['status'],
            'error_message': row['error_message'],
            'created_at': row['created_at']
        })

    return jsonify({'success': True, 'logs': logs})


@login_required
def api_get_failed_refresh_logs() -> Any:
    """获取所有失败的刷新记录"""
    db = get_db()

    # 获取每个账号最近一次失败的刷新记录
    cursor = db.execute('''
        SELECT l.*, a.email as account_email, a.status as account_status
        FROM account_refresh_logs l
        INNER JOIN (
            SELECT account_id, MAX(created_at) as last_refresh
            FROM account_refresh_logs
            GROUP BY account_id
        ) latest ON l.account_id = latest.account_id AND l.created_at = latest.last_refresh
        LEFT JOIN accounts a ON l.account_id = a.id
        WHERE l.status = 'failed'
        ORDER BY l.created_at DESC
    ''')

    logs = []
    for row in cursor.fetchall():
        logs.append({
            'id': row['id'],
            'account_id': row['account_id'],
            'account_email': row['account_email'] or row['account_email'],
            'account_status': row['account_status'],
            'refresh_type': row['refresh_type'],
            'status': row['status'],
            'error_message': row['error_message'],
            'created_at': row['created_at']
        })

    return jsonify({'success': True, 'logs': logs})


@login_required
def api_get_refresh_stats() -> Any:
    """获取刷新统计信息（统计当前失败状态的邮箱数量）"""
    db = get_db()

    cursor = db.execute('''
        SELECT MAX(created_at) as last_refresh_time
        FROM account_refresh_logs
        WHERE refresh_type IN ('manual', 'manual_all', 'scheduled', 'retry')
    ''')
    row = cursor.fetchone()
    last_refresh_time = row['last_refresh_time'] if row else None

    cursor = db.execute('''
        SELECT COUNT(*) as total_accounts
        FROM accounts
        WHERE status = 'active'
    ''')
    total_accounts = cursor.fetchone()['total_accounts']

    cursor = db.execute('''
        SELECT COUNT(DISTINCT l.account_id) as failed_count
        FROM account_refresh_logs l
        INNER JOIN (
            SELECT account_id, MAX(created_at) as last_refresh
            FROM account_refresh_logs
            GROUP BY account_id
        ) latest ON l.account_id = latest.account_id AND l.created_at = latest.last_refresh
        INNER JOIN accounts a ON l.account_id = a.id
        WHERE l.status = 'failed' AND a.status = 'active'
    ''')
    failed_count = cursor.fetchone()['failed_count']

    return jsonify({
        'success': True,
        'stats': {
            'total': total_accounts,
            'success_count': total_accounts - failed_count,
            'failed_count': failed_count,
            'last_refresh_time': last_refresh_time
        }
    })
