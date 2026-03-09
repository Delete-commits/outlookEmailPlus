from __future__ import annotations

from typing import Dict

from outlook_web import config
from outlook_web.db import get_db
from outlook_web.security.crypto import decrypt_data


def get_setting(key: str, default: str = "") -> str:
    """获取设置值"""
    db = get_db()
    cursor = db.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> bool:
    """设置值"""
    db = get_db()
    try:
        db.execute(
            """
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (key, value),
        )
        db.commit()
        return True
    except Exception:
        return False


def get_all_settings() -> Dict[str, str]:
    """获取所有设置"""
    db = get_db()
    cursor = db.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    return {row["key"]: row["value"] for row in rows}


def get_login_password() -> str:
    """获取登录密码（优先从数据库读取）"""
    password = get_setting("login_password")
    return password if password else config.get_login_password_default()


def get_gptmail_api_key() -> str:
    """获取 GPTMail API Key（优先从数据库读取）"""
    api_key = get_setting("gptmail_api_key")
    return api_key if api_key else config.get_gptmail_api_key_default()


def get_external_api_key() -> str:
    """
    获取对外开放 API Key。

    - 若数据库为空，返回空字符串
    - 若为 enc: 加密格式，自动解密
    - 若为历史明文（兼容），直接返回明文
    - 解密失败时返回空字符串（避免影响外部接口鉴权逻辑）
    """
    value = get_setting("external_api_key") or ""
    if not value:
        return ""
    try:
        return decrypt_data(value)
    except Exception:
        return ""


def get_external_api_key_masked(head: int = 4, tail: int = 4) -> str:
    """对外 API Key 脱敏展示：前 N 位 + 若干 * + 后 N 位。"""
    key = get_external_api_key()
    if not key:
        return ""
    safe_value = str(key)
    if len(safe_value) <= head + tail:
        return "*" * len(safe_value)
    return safe_value[:head] + ("*" * (len(safe_value) - head - tail)) + safe_value[-tail:]
