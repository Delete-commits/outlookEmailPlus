from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple

from outlook_web.audit import log_audit
from outlook_web.repositories import accounts as accounts_repo
from outlook_web.repositories import groups as groups_repo
from outlook_web.services import graph as graph_service
from outlook_web.services import imap as imap_service
from outlook_web.services.imap_generic import get_email_detail_imap_generic, get_emails_imap_generic
from outlook_web.services.verification_extractor import extract_email_text, extract_verification_info_with_options

# Outlook IMAP 回退服务器（保持与内部接口一致）
IMAP_SERVER_NEW = "outlook.live.com"
IMAP_SERVER_OLD = "outlook.office365.com"

# wait-message 约束
MAX_TIMEOUT_SECONDS = 120


class ExternalApiError(Exception):
    code = "INTERNAL_ERROR"
    status = 500

    def __init__(self, message: str, *, data: Any = None):
        super().__init__(message)
        self.message = message
        self.data = data


class InvalidParamError(ExternalApiError):
    code = "INVALID_PARAM"
    status = 400


class AccountNotFoundError(ExternalApiError):
    code = "ACCOUNT_NOT_FOUND"
    status = 404


class MailNotFoundError(ExternalApiError):
    code = "MAIL_NOT_FOUND"
    status = 404


class VerificationCodeNotFoundError(ExternalApiError):
    code = "VERIFICATION_CODE_NOT_FOUND"
    status = 404


class VerificationLinkNotFoundError(ExternalApiError):
    code = "VERIFICATION_LINK_NOT_FOUND"
    status = 404


class ProxyError(ExternalApiError):
    code = "PROXY_ERROR"
    status = 502


class UpstreamReadFailedError(ExternalApiError):
    code = "UPSTREAM_READ_FAILED"
    status = 502


def ok(data: Any = None, *, message: str = "success") -> Dict[str, Any]:
    return {"success": True, "code": "OK", "message": message, "data": data}


def fail(code: str, message: str, *, data: Any = None) -> Dict[str, Any]:
    return {"success": False, "code": code, "message": message, "data": data}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None

    # 1) ISO 8601（Graph 常见：2026-03-08T12:00:00Z）
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # 2) RFC2822（IMAP Date header 常见）
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _format_datetime(dt: Optional[datetime], fallback: str = "") -> tuple[str, int]:
    if not dt:
        return (fallback or "", 0)
    try:
        dt = dt.astimezone(timezone.utc).replace(microsecond=0)
        return (dt.isoformat().replace("+00:00", "Z"), int(dt.timestamp()))
    except Exception:
        return (fallback or "", 0)


def _extract_email_address(value: str) -> str:
    """从 `Name <addr>` 中提取 addr；解析失败则原样返回。"""
    try:
        _name, addr = parseaddr(str(value or ""))
        return addr or str(value or "")
    except Exception:
        return str(value or "")


def _build_message_summary(email_addr: str, item: Dict[str, Any], *, method: str) -> Dict[str, Any]:
    raw_from = item.get("from")
    if isinstance(raw_from, dict):
        from_address = (raw_from.get("emailAddress") or {}).get("address") or ""
    else:
        from_address = str(raw_from or item.get("from_address") or "")
    from_address = _extract_email_address(from_address)

    subject = str(item.get("subject") or "无主题")

    created_at_raw = (
        item.get("receivedDateTime")
        or item.get("date")
        or item.get("created_at")
        or item.get("received_at")
        or ""
    )
    created_dt = _parse_datetime(str(created_at_raw))
    created_at, timestamp = _format_datetime(created_dt, str(created_at_raw))

    content_preview = str(
        item.get("bodyPreview")
        or item.get("body_preview")
        or item.get("content_preview")
        or item.get("bodyPreview")
        or ""
    )

    is_read = bool(item.get("isRead") if "isRead" in item else item.get("is_read") or item.get("isRead") or False)

    return {
        "id": str(item.get("id") or ""),
        "email_address": email_addr,
        "from_address": from_address,
        "subject": subject,
        "content_preview": content_preview,
        "has_html": bool(item.get("has_html") or False),
        "timestamp": timestamp,
        "created_at": created_at,
        "is_read": is_read,
        "method": method,
    }


def _get_proxy_url(account: Dict[str, Any]) -> str:
    proxy_url = ""
    group_id = account.get("group_id")
    if not group_id:
        return ""
    group = groups_repo.get_group_by_id(group_id)
    if group:
        proxy_url = group.get("proxy_url", "") or ""
    return proxy_url


def require_account(email_addr: str) -> Dict[str, Any]:
    email_addr = (email_addr or "").strip()
    if not email_addr:
        raise InvalidParamError("email 参数不能为空")
    if "@" not in email_addr:
        raise InvalidParamError("email 参数无效")
    account = accounts_repo.get_account_by_email(email_addr)
    if not account:
        raise AccountNotFoundError("账号不存在", data={"email": email_addr})
    return account


def list_messages_for_external(
    *,
    email_addr: str,
    folder: str = "inbox",
    skip: int = 0,
    top: int = 20,
) -> Tuple[List[Dict[str, Any]], str]:
    account = require_account(email_addr)
    folder = (folder or "inbox").strip().lower() or "inbox"
    skip = max(0, int(skip or 0))
    top = max(1, min(int(top or 20), 50))

    account_type = (account.get("account_type") or "outlook").strip().lower()
    if account_type == "imap":
        result = get_emails_imap_generic(
            email_addr=email_addr,
            imap_password=account.get("imap_password", "") or "",
            imap_host=account.get("imap_host", "") or "",
            imap_port=account.get("imap_port", 993) or 993,
            folder=folder,
            provider=account.get("provider", "_default") or "_default",
            skip=skip,
            top=top,
        )
        if not result.get("success"):
            raise UpstreamReadFailedError("IMAP 读取失败", data=result.get("error"))
        method_label = str(result.get("method") or "IMAP (Generic)")
        emails = [_build_message_summary(email_addr, e, method=method_label) for e in (result.get("emails") or [])]
        return emails, method_label

    proxy_url = _get_proxy_url(account)

    graph_result = graph_service.get_emails_graph(
        account.get("client_id") or "",
        account.get("refresh_token") or "",
        folder=folder,
        skip=skip,
        top=top,
        proxy_url=proxy_url,
    )
    if graph_result.get("success"):
        method_label = "Graph API"
        emails = [_build_message_summary(email_addr, e, method=method_label) for e in (graph_result.get("emails") or [])]
        return emails, method_label

    graph_error = graph_result.get("error")
    if isinstance(graph_error, dict) and graph_error.get("type") in ("ProxyError", "ConnectionError"):
        raise ProxyError("代理连接失败", data=graph_error)

    # Graph 失败 → IMAP(New) → IMAP(Old) 回退
    imap_new_result = imap_service.get_emails_imap_with_server(
        email_addr,
        account.get("client_id") or "",
        account.get("refresh_token") or "",
        folder,
        skip,
        top,
        IMAP_SERVER_NEW,
    )
    if imap_new_result.get("success"):
        method_label = "IMAP (New)"
        emails = [_build_message_summary(email_addr, e, method=method_label) for e in (imap_new_result.get("emails") or [])]
        return emails, method_label

    imap_old_result = imap_service.get_emails_imap_with_server(
        email_addr,
        account.get("client_id") or "",
        account.get("refresh_token") or "",
        folder,
        skip,
        top,
        IMAP_SERVER_OLD,
    )
    if imap_old_result.get("success"):
        method_label = "IMAP (Old)"
        emails = [_build_message_summary(email_addr, e, method=method_label) for e in (imap_old_result.get("emails") or [])]
        return emails, method_label

    raise UpstreamReadFailedError(
        "Graph/IMAP 均读取失败",
        data={"graph": graph_error, "imap_new": imap_new_result.get("error"), "imap_old": imap_old_result.get("error")},
    )


def filter_messages(
    emails: List[Dict[str, Any]],
    *,
    from_contains: str = "",
    subject_contains: str = "",
    since_minutes: Optional[int] = None,
) -> List[Dict[str, Any]]:
    from_contains = (from_contains or "").strip().lower()
    subject_contains = (subject_contains or "").strip().lower()

    since_dt: Optional[datetime] = None
    if since_minutes is not None:
        try:
            since_minutes_int = int(since_minutes)
            if since_minutes_int > 0:
                since_dt = _utcnow() - timedelta(minutes=since_minutes_int)
        except Exception:
            since_dt = None

    filtered: List[Dict[str, Any]] = []
    for e in emails or []:
        from_addr = str(e.get("from_address") or e.get("from") or "").lower()
        subj = str(e.get("subject") or "").lower()
        if from_contains and from_contains not in from_addr:
            continue
        if subject_contains and subject_contains not in subj:
            continue

        if since_dt is not None:
            dt = _parse_datetime(e.get("created_at") or e.get("date") or e.get("receivedDateTime") or "")
            if dt and dt < since_dt:
                continue

        filtered.append(e)
    return filtered


def get_latest_message_for_external(
    *,
    email_addr: str,
    folder: str = "inbox",
    from_contains: str = "",
    subject_contains: str = "",
    since_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    emails = list_messages_for_external(email_addr=email_addr, folder=folder, skip=0, top=20)[0]
    filtered = filter_messages(
        emails,
        from_contains=from_contains,
        subject_contains=subject_contains,
        since_minutes=since_minutes,
    )
    if not filtered:
        raise MailNotFoundError("未找到匹配邮件", data={"email": email_addr})
    # 保险起见按 timestamp 再排序一次（不同读取链路可能不严格有序）
    filtered.sort(key=lambda x: int(x.get("timestamp") or 0), reverse=True)
    return filtered[0]


def get_message_detail_for_external(
    *,
    email_addr: str,
    message_id: str,
    folder: str = "inbox",
) -> Dict[str, Any]:
    account = require_account(email_addr)
    message_id = (message_id or "").strip()
    if not message_id:
        raise InvalidParamError("message_id 不能为空")

    folder = (folder or "inbox").strip().lower() or "inbox"
    account_type = (account.get("account_type") or "outlook").strip().lower()

    if account_type == "imap":
        detail = get_email_detail_imap_generic(
            email_addr=email_addr,
            imap_password=account.get("imap_password", "") or "",
            imap_host=account.get("imap_host", "") or "",
            imap_port=account.get("imap_port", 993) or 993,
            message_id=message_id,
            folder=folder,
            provider=account.get("provider", "_default") or "_default",
        )
        if not detail:
            raise MailNotFoundError("未找到邮件详情", data={"email": email_addr, "message_id": message_id})

        html_content = str(detail.get("body_html") or "")
        content = str(detail.get("body_text") or "") or extract_email_text({"body_html": html_content})
        raw_content = str(detail.get("raw_content") or "")
        created_at_raw = str(detail.get("date") or "")
        created_at, timestamp = _format_datetime(_parse_datetime(created_at_raw), created_at_raw)
        return {
            "id": detail.get("id") or message_id,
            "email_address": email_addr,
            "from_address": _extract_email_address(detail.get("from") or ""),
            "to_address": detail.get("to") or "",
            "subject": detail.get("subject") or "",
            "content": content,
            "html_content": html_content,
            "raw_content": raw_content,
            "timestamp": timestamp,
            "created_at": created_at,
            "has_html": bool(html_content),
            "method": "IMAP (Generic)",
        }

    proxy_url = _get_proxy_url(account)

    detail = graph_service.get_email_detail_graph(
        account.get("client_id") or "",
        account.get("refresh_token") or "",
        message_id,
        proxy_url,
    )
    method_label = "Graph API"
    if not detail:
        detail = imap_service.get_email_detail_imap_with_server(
            email_addr,
            account.get("client_id") or "",
            account.get("refresh_token") or "",
            message_id,
            folder,
            IMAP_SERVER_NEW,
        )
        method_label = "IMAP (New)"

    if not detail:
        detail = imap_service.get_email_detail_imap_with_server(
            email_addr,
            account.get("client_id") or "",
            account.get("refresh_token") or "",
            message_id,
            folder,
            IMAP_SERVER_OLD,
        )
        method_label = "IMAP (Old)"

    if not detail:
        raise MailNotFoundError("未找到邮件详情", data={"email": email_addr, "message_id": message_id})

    created_at_raw = ""
    timestamp = 0
    created_at = ""

    if "body" in detail and isinstance(detail.get("body"), dict):
        body_obj = detail.get("body") or {}
        body_type = str(body_obj.get("contentType") or "text").lower()
        body_content = str(body_obj.get("content") or "")

        html_content = body_content if body_type == "html" else ""
        content = body_content if body_type == "text" else extract_email_text({"body_html": html_content})
        raw_content = body_content

        from_address = (detail.get("from") or {}).get("emailAddress", {}).get("address", "")
        to_address = ",".join([r.get("emailAddress", {}).get("address", "") for r in (detail.get("toRecipients") or [])])
        created_at_raw = str(detail.get("receivedDateTime") or "")
        subject = str(detail.get("subject") or "")
    else:
        # IMAP dict 格式
        content = str(detail.get("body") or "")
        html_content = ""
        raw_content = str(detail.get("raw_content") or content)
        from_address = _extract_email_address(str(detail.get("from") or ""))
        to_address = str(detail.get("to") or "")
        created_at_raw = str(detail.get("date") or "")
        subject = str(detail.get("subject") or "")

    created_at, timestamp = _format_datetime(_parse_datetime(created_at_raw), created_at_raw)

    return {
        "id": message_id,
        "email_address": email_addr,
        "from_address": _extract_email_address(from_address),
        "to_address": to_address,
        "subject": subject,
        "content": content,
        "html_content": html_content,
        "raw_content": raw_content,
        "timestamp": timestamp,
        "created_at": created_at,
        "has_html": bool(html_content),
        "method": method_label,
    }


def get_verification_result(
    *,
    email_addr: str,
    folder: str = "inbox",
    from_contains: str = "",
    subject_contains: str = "",
    since_minutes: Optional[int] = None,
    code_regex: str | None = None,
    code_length: str | None = None,
    code_source: str = "all",
) -> Dict[str, Any]:
    latest_summary = get_latest_message_for_external(
        email_addr=email_addr,
        folder=folder,
        from_contains=from_contains,
        subject_contains=subject_contains,
        since_minutes=since_minutes,
    )
    message_id = str(latest_summary.get("id") or "")
    method = str(latest_summary.get("method") or "")

    detail = get_message_detail_for_external(email_addr=email_addr, message_id=message_id, folder=folder)

    email_obj = {
        "subject": detail.get("subject") or "",
        "body": detail.get("content") or "",
        "body_html": detail.get("html_content") or "",
        "body_preview": latest_summary.get("content_preview") or "",
    }
    extracted = extract_verification_info_with_options(
        email_obj,
        code_regex=code_regex,
        code_length=code_length,
        code_source=code_source,
    )
    extracted["email"] = email_addr
    extracted["matched_email_id"] = message_id
    extracted["from"] = detail.get("from_address") or latest_summary.get("from_address") or ""
    extracted["subject"] = detail.get("subject") or latest_summary.get("subject") or ""
    extracted["received_at"] = detail.get("created_at") or latest_summary.get("created_at") or ""
    extracted["method"] = detail.get("method") or method
    return extracted


def wait_for_message(
    *,
    email_addr: str,
    timeout_seconds: int = 30,
    poll_interval: int = 5,
    folder: str = "inbox",
    from_contains: str = "",
    subject_contains: str = "",
    since_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    try:
        timeout_seconds = int(timeout_seconds)
        poll_interval = int(poll_interval)
    except Exception as exc:
        raise InvalidParamError("timeout_seconds/poll_interval 参数无效") from exc

    if timeout_seconds <= 0 or timeout_seconds > MAX_TIMEOUT_SECONDS:
        raise InvalidParamError(f"timeout_seconds 必须在 1-{MAX_TIMEOUT_SECONDS} 秒之间")
    if poll_interval <= 0 or poll_interval > timeout_seconds:
        raise InvalidParamError("poll_interval 参数无效")

    start = time.time()
    last_error: Optional[ExternalApiError] = None
    while True:
        try:
            return get_latest_message_for_external(
                email_addr=email_addr,
                folder=folder,
                from_contains=from_contains,
                subject_contains=subject_contains,
                since_minutes=since_minutes,
            )
        except MailNotFoundError as exc:
            last_error = exc

        if time.time() - start >= timeout_seconds:
            raise MailNotFoundError("等待超时，未检测到匹配邮件", data={"email": email_addr}) from last_error

        time.sleep(poll_interval)


def audit_external_api_access(
    *,
    action: str,
    email_addr: str,
    endpoint: str,
    status: str,
    details: Dict[str, Any] | None = None,
):
    safe_details: Dict[str, Any] = {"endpoint": endpoint, "status": status}
    if details:
        # 避免日志中输出敏感信息（如 API Key）
        safe_details.update(details)

    try:
        details_text = json.dumps(safe_details, ensure_ascii=False)
    except Exception:
        details_text = str(safe_details)

    log_audit(action, "external_api", email_addr, details_text)
