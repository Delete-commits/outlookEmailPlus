# TDD-00008｜对外验证码与邮件读取开放 API — 技术设计细节文档

- **文档编号**: TDD-00008
- **创建日期**: 2026-03-08
- **版本**: V1.0
- **状态**: 草案
- **对齐 PRD**: `docs/PRD/PRD-00008-对外验证码与邮件读取开放API.md`
- **对齐 FD**: `docs/FD/FD-00008-对外验证码与邮件读取开放API.md`
- **对齐 OpenAPI**: `docs/FD/OPENAPI-00008-对外验证码与邮件读取开放API.yaml`
- **前置依赖**: `docs/TDD/TDD-00005-多邮箱统一管理.md`（账号结构、Graph/IMAP 链路、模块化 Blueprint 架构）

---

## 目录

1. [文档目的](#1-文档目的)
2. [设计原则与硬约束](#2-设计原则与硬约束)
3. [总体技术架构与数据流](#3-总体技术架构与数据流)
4. [文件变更清单](#4-文件变更清单)
5. [设置与鉴权技术细节](#5-设置与鉴权技术细节)
6. [Route 层技术细节](#6-route-层技术细节)
7. [Controller 层技术细节](#7-controller-层技术细节)
8. [External Service 层技术细节](#8-external-service-层技术细节)
9. [邮件读取与回退链路细节](#9-邮件读取与回退链路细节)
10. [验证码与验证链接提取细节](#10-验证码与验证链接提取细节)
11. [统一响应与错误码映射](#11-统一响应与错误码映射)
12. [系统自检接口实现细节](#12-系统自检接口实现细节)
13. [前端设置页改造细节](#13-前端设置页改造细节)
14. [兼容性与回归保障](#14-兼容性与回归保障)
15. [测试策略与测试用例](#15-测试策略与测试用例)
16. [实施顺序建议](#16-实施顺序建议)

---

## 1. 文档目的

本 TDD 描述 PRD-00008「对外验证码与邮件读取开放 API」的**完整技术实现细节**，重点回答：

- 如何在不破坏现有内部接口的前提下，新增一套 `X-API-Key` 鉴权的开放接口
- 如何把现有内部邮件读取能力抽象成可复用的开放 Service，而不是继续堆叠在 controller 中
- 如何实现验证码与验证链接的**可配置提取规则**（`code_regex` / `code_length` / `code_source`）
- 如何保证开放接口、设置页、审计日志、健康检查三者闭环
- 如何让 OpenAPI 草稿中的字段、错误码、返回结构与真实代码实现保持一致

---

## 2. 设计原则与硬约束

### 2.1 API 与模块边界硬约束

- **新增路由前缀固定**：所有开放接口统一以 `/api/external` 开头
- **不修改现有内部接口 URL**：
  - `GET /api/emails/<email_addr>`
  - `GET /api/emails/<email_addr>/extract-verification`
  - `GET /api/email/<email_addr>/<message_id>`
  保持不变
- **开放接口不依赖 Session**：只能走 `X-API-Key`，不能走 `login_required`
- **开放接口响应结构统一**：固定为 `success/code/message/data`
- **开放接口首版仅开放读能力**：不新增外部删除、移动、已读等写操作

### 2.2 数据与安全硬约束

- **不新增数据库表**：复用 `settings`、`accounts`、`groups`、`audit_logs`
- **`external_api_key` 建议加密存储**：使用现有 `encrypt_data()` / `decrypt_data()`
- **设置页不回显明文 API Key**：仅返回 `*_set`、`*_masked`
- **日志中不允许输出明文 API Key**
- **查询参数中不接受 `api_key`**：根项目不沿用示例项目的 query 传 key 方案

### 2.3 向后兼容原则

- `outlook_web/controllers/emails.py` 中现有内部 API 行为与响应结构不变
- `outlook_web/controllers/settings.py` 中现有设置项行为不变，仅扩展开放 API Key 字段
- Graph → IMAP(New) → IMAP(Old) 的读取回退顺序保持不变
- 现有 `verification_extractor.py` 默认提取逻辑不破坏，仅在外部接口场景补充参数化入口

---

## 3. 总体技术架构与数据流

### 3.1 获取验证码主链路

```text
客户端
  ↓ GET /api/external/verification-code
Route: outlook_web/routes/emails.py
  ↓
Security: api_key_required
  ↓
Controller: api_external_get_verification_code()
  ↓
Repository: accounts_repo.get_account_by_email(email)
  ↓
Service: external_api.get_latest_message_for_external(...)
  ↓
Service: _read_emails_with_fallback(account, folder, skip=0, top=N)
  ├─ graph_service.get_emails_graph(...)
  ├─ imap_service.get_emails_imap_with_server(..., IMAP_SERVER_NEW)
  └─ imap_service.get_emails_imap_with_server(..., IMAP_SERVER_OLD)
  ↓
Service: _read_email_detail_with_fallback(account, message_id, folder)
  ↓
Service: verification_extractor.extract_verification_info_with_options(...)
  ↓
Service: ok()/fail() 统一包装
  ↓
Audit: log_audit("external_api_access", ...)
  ↓
返回 JSON
```

### 3.2 人工排查详情链路

```text
客户端
  ↓ GET /api/external/messages/{message_id}?email=...
api_key_required
  ↓
Controller 校验 email/message_id
  ↓
Service 获取 account
  ↓
Service 读取详情（Graph 优先，IMAP 回退）
  ↓
Service 组装 MessageDetail
  ↓
返回统一响应
```

### 3.3 设置页配置链路

```text
前端 settings 页面
  ↓ GET /api/settings
controllers/settings.py
  ↓
repositories/settings.py
  ↓
返回 external_api_key_set / external_api_key_masked

前端保存 settings
  ↓ PUT /api/settings
controllers/settings.py
  ↓
encrypt_data(external_api_key)
  ↓
repositories/settings.py.set_setting('external_api_key', encrypted)
```

---

## 4. 文件变更清单

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `outlook_web/security/auth.py` | **修改** | 新增 `api_key_required()` |
| `outlook_web/repositories/settings.py` | **修改** | 新增 `get_external_api_key()`、`get_external_api_key_masked()` |
| `outlook_web/controllers/settings.py` | **修改** | 扩展 `external_api_key` 读写与脱敏展示 |
| `outlook_web/db.py` | **修改** | 初始化默认 `external_api_key` setting |
| `outlook_web/routes/emails.py` | **修改** | 注册开放消息与验证接口 |
| `outlook_web/routes/system.py` | **修改** | 注册开放系统接口 |
| `outlook_web/controllers/emails.py` | **修改** | 新增开放 API 控制器函数 |
| `outlook_web/controllers/system.py` | **修改** | 新增开放健康检查/能力/账号状态函数 |
| `outlook_web/services/external_api.py` | **新增** | 外部接口专用 service 层 |
| `outlook_web/services/verification_extractor.py` | **修改** | 增强参数化提取入口 |
| `templates/index.html` | **修改** | 设置页增加开放 API Key 配置区块 |
| `static/js/main.js` | **修改** | 读取/保存开放 API Key |
| `tests/test_external_api.py` | **新增** | 契约/集成测试 |
| `tests/test_settings_external_api_key.py` | **新增/可选** | 设置项测试 |

---

## 5. 设置与鉴权技术细节

### 5.1 `settings` 表 Key 设计

复用 `settings` 表，不新增 schema。新增 key：

| Key | 默认值 | 存储方式 | 说明 |
|---|---|---|---|
| `external_api_key` | `""` | 建议加密 | 对外开放接口使用的 API Key |

### 5.2 `db.py` 初始化逻辑

文件：`outlook_web/db.py`

在 `init_db()` 的默认 settings 初始化阶段增加：

```python
cursor.execute(
    """
    INSERT OR IGNORE INTO settings (key, value)
    VALUES ('external_api_key', '')
    """
)
```

说明：
- 不修改 `DB_SCHEMA_VERSION`
- 因为只是新增默认配置，不涉及 schema 变更
- 对既有数据库幂等生效

### 5.3 `repositories/settings.py` 技术设计

新增函数：

```python
def get_external_api_key() -> str:
    """
    获取对外 API Key。
    - 若值为空，返回空字符串
    - 若值使用 enc: 前缀加密，自动解密
    - 若值为历史明文（兼容老数据），直接返回明文
    """


def get_external_api_key_masked() -> str:
    """
    返回脱敏展示值。
    规则：前 4 位 + 若干 * + 后 4 位；长度不足时返回全 *。
    """
```

建议实现：

```python
from outlook_web.security.crypto import decrypt_data, is_encrypted


def get_external_api_key() -> str:
    value = get_setting("external_api_key", "")
    if not value:
        return ""
    if is_encrypted(value):
        try:
            return decrypt_data(value)
        except Exception:
            return ""
    return value
```

### 5.4 `api_key_required()` 技术设计

文件：`outlook_web/security/auth.py`

新增：

```python
from outlook_web.repositories.settings import get_external_api_key


def api_key_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = (request.headers.get("X-API-Key") or "").strip()
        if not api_key:
            return jsonify({
                "success": False,
                "code": "UNAUTHORIZED",
                "message": "API Key 缺失或无效",
                "data": None,
            }), 401

        stored_key = get_external_api_key()
        if not stored_key:
            return jsonify({
                "success": False,
                "code": "API_KEY_NOT_CONFIGURED",
                "message": "系统未配置对外 API Key",
                "data": None,
            }), 403

        if api_key != stored_key:
            return jsonify({
                "success": False,
                "code": "UNAUTHORIZED",
                "message": "API Key 缺失或无效",
                "data": None,
            }), 401

        return f(*args, **kwargs)
    return decorated_function
```

### 5.5 鉴权实现注意点

- 不复用 `build_error_payload()`，因为开放接口返回结构已在 OpenAPI 中固定为简化结构
- 不跳转登录页面
- 不读取 query 参数中的 `api_key`
- 所有开放接口 controller 必须直接使用 `@api_key_required`

---

## 6. Route 层技术细节

### 6.1 `outlook_web/routes/emails.py`

在现有内部路由后追加：

```python
bp.add_url_rule(
    "/api/external/messages",
    view_func=emails_controller.api_external_get_messages,
    methods=["GET"],
)
bp.add_url_rule(
    "/api/external/messages/latest",
    view_func=emails_controller.api_external_get_latest_message,
    methods=["GET"],
)
bp.add_url_rule(
    "/api/external/messages/<path:message_id>",
    view_func=emails_controller.api_external_get_message_detail,
    methods=["GET"],
)
bp.add_url_rule(
    "/api/external/messages/<path:message_id>/raw",
    view_func=emails_controller.api_external_get_message_raw,
    methods=["GET"],
)
bp.add_url_rule(
    "/api/external/verification-code",
    view_func=emails_controller.api_external_get_verification_code,
    methods=["GET"],
)
bp.add_url_rule(
    "/api/external/verification-link",
    view_func=emails_controller.api_external_get_verification_link,
    methods=["GET"],
)
bp.add_url_rule(
    "/api/external/wait-message",
    view_func=emails_controller.api_external_wait_message,
    methods=["GET"],
)
```

说明：
- 统一放在 `emails` Blueprint 内，避免额外新建 Blueprint
- 与内部邮件能力聚合，减少初始化改动

### 6.2 `outlook_web/routes/system.py`

追加：

```python
bp.add_url_rule(
    "/api/external/health",
    view_func=system_controller.api_external_health,
    methods=["GET"],
)
bp.add_url_rule(
    "/api/external/capabilities",
    view_func=system_controller.api_external_capabilities,
    methods=["GET"],
)
bp.add_url_rule(
    "/api/external/account-status",
    view_func=system_controller.api_external_account_status,
    methods=["GET"],
)
```

---

## 7. Controller 层技术细节

### 7.1 `controllers/emails.py` 新增函数清单

```python
@api_key_required
def api_external_get_messages() -> Any: ...

@api_key_required
def api_external_get_latest_message() -> Any: ...

@api_key_required
def api_external_get_message_detail(message_id: str) -> Any: ...

@api_key_required
def api_external_get_message_raw(message_id: str) -> Any: ...

@api_key_required
def api_external_get_verification_code() -> Any: ...

@api_key_required
def api_external_get_verification_link() -> Any: ...

@api_key_required
def api_external_wait_message() -> Any: ...
```

### 7.2 Controller 只做三件事

1. 解析并校验参数
2. 调用 `services/external_api.py`
3. 写审计日志并返回统一响应

### 7.3 参数解析辅助函数

建议在 `controllers/emails.py` 内新增：

```python
def _parse_external_args() -> dict:
    folder = (request.args.get("folder", "inbox") or "inbox").strip().lower()
    if folder not in {"inbox", "junkemail", "deleteditems"}:
        raise ValueError("folder 参数无效")

    top = int(request.args.get("top", 20))
    if top < 1 or top > 50:
        raise ValueError("top 参数无效")

    skip = int(request.args.get("skip", 0))
    if skip < 0:
        raise ValueError("skip 参数无效")

    return {
        "email": (request.args.get("email", "") or "").strip(),
        "folder": folder,
        "skip": skip,
        "top": top,
        "from_contains": (request.args.get("from_contains", "") or "").strip(),
        "subject_contains": (request.args.get("subject_contains", "") or "").strip(),
        "since_minutes": request.args.get("since_minutes"),
        "code_length": (request.args.get("code_length", "") or "").strip(),
        "code_regex": (request.args.get("code_regex", "") or "").strip(),
        "code_source": (request.args.get("code_source", "all") or "all").strip().lower(),
        "timeout_seconds": request.args.get("timeout_seconds"),
        "poll_interval": request.args.get("poll_interval"),
    }
```

### 7.4 参数校验约束

| 参数 | 校验规则 |
|---|---|
| `email` | 必填，必须含 `@` |
| `folder` | `inbox/junkemail/deleteditems` |
| `top` | `1-50` |
| `skip` | `>=0` |
| `since_minutes` | `>=1` |
| `timeout_seconds` | `1-120` |
| `poll_interval` | `1-30` 且 `< timeout_seconds` |
| `code_source` | `subject/content/html/all` |
| `code_length` | 匹配 `^\d+-\d+$` |

### 7.5 审计日志实现约定

每个开放接口在 controller 末尾统一记录：

```python
log_audit(
    action="external_api_access",
    resource_type="external_api",
    resource_id=email_addr,
    details=json.dumps(
        {
            "path": request.path,
            "result": "success",
            "method": payload_method,
            "error_code": "",
        },
        ensure_ascii=False,
    ),
)
```

失败分支同样记录 `result=failed` 与 `error_code`。

---

## 8. External Service 层技术细节

### 8.1 新增文件：`outlook_web/services/external_api.py`

该模块负责承接开放接口通用逻辑，避免 `controllers/emails.py` 继续膨胀。

### 8.2 模块函数清单

```python
def ok(data, message: str = "success") -> dict:
    return {"success": True, "code": "OK", "message": message, "data": data}


def fail(code: str, message: str, status: int, data=None):
    return jsonify({"success": False, "code": code, "message": message, "data": data}), status


def list_messages_for_external(... ) -> dict: ...
def get_latest_message_for_external(... ) -> dict: ...
def get_message_detail_for_external(... ) -> dict: ...
def get_message_raw_for_external(... ) -> dict: ...
def extract_verification_code_for_external(... ) -> dict: ...
def extract_verification_link_for_external(... ) -> dict: ...
def wait_message_for_external(... ) -> dict: ...
```

### 8.3 `list_messages_for_external()` 设计

输入：
- `email_addr`
- `folder`
- `skip`
- `top`
- `from_contains`
- `subject_contains`
- `since_minutes`

输出：

```python
{
    "emails": [...],
    "count": 2,
    "has_more": False,
}
```

实现步骤：

1. `accounts_repo.get_account_by_email(email_addr)`
2. `_read_emails_with_fallback(account, folder, skip, top)`
3. 将读取结果统一映射成 `MessageSummary`
4. 按 `from_contains`、`subject_contains`、`since_minutes` 在 service 层二次过滤
5. 返回过滤后结果

### 8.4 `get_latest_message_for_external()`

实现：
- 直接调用 `list_messages_for_external(..., skip=0, top=max(top, 20))`
- 若 `emails` 为空，抛 `MailNotFoundError`
- 返回 `emails[0]`

### 8.5 `get_message_detail_for_external()`

实现：
1. 获取账号
2. 调用 `_read_email_detail_with_fallback()`
3. 统一映射为：

```python
{
    "id": ...,
    "email_address": email_addr,
    "from_address": ...,
    "to_address": ...,
    "subject": ...,
    "content": ...,
    "html_content": ...,
    "raw_content": ...,
    "timestamp": ...,
    "created_at": ...,
    "has_html": True/False,
    "method": "Graph API" | "IMAP (New)" | "IMAP (Old)",
}
```

### 8.6 `wait_message_for_external()`

伪码：

```python
start = time.time()
while time.time() - start < timeout_seconds:
    result = get_latest_message_for_external(...)
    if result:
        return result
    time.sleep(poll_interval)
raise MailNotFoundError("等待超时，未检测到匹配邮件")
```

注意：
- 最大超时 120 秒
- 默认 30 秒
- 不使用异步任务，不引入 scheduler

---

## 9. 邮件读取与回退链路细节

### 9.1 `_read_emails_with_fallback()`

建议从 `controllers/emails.py` 现有逻辑下沉到 `services/external_api.py`。

函数签名：

```python
def _read_emails_with_fallback(account: dict, folder: str, skip: int, top: int) -> dict:
    """
    返回:
    {
        "success": True,
        "emails": [...],
        "method": "Graph API"
    }
    或抛出可识别异常。
    """
```

### 9.2 Graph 优先读取

```python
graph_result = graph_service.get_emails_graph(
    account["client_id"],
    account["refresh_token"],
    folder,
    skip,
    top,
    proxy_url,
)
```

成功：
- 直接返回
- `method = "Graph API"`

失败：
- 收集 `graph_error`
- 若是 `ProxyError` / `ConnectionError`，直接中止并抛 `ProxyError`

### 9.3 IMAP 回退读取

按顺序：

1. `IMAP_SERVER_NEW = "outlook.live.com"`
2. `IMAP_SERVER_OLD = "outlook.office365.com"`

成功时返回 `method = "IMAP (New)"` 或 `"IMAP (Old)"`

### 9.4 `_read_email_detail_with_fallback()`

实现顺序：

1. `graph_service.get_email_detail_graph()`
2. `imap_service.get_email_detail_imap(..., folder)`
3. 若都失败，抛 `UpstreamReadFailedError`

### 9.5 非 Outlook IMAP 兼容说明

当前开放 API 第一版目标是 Outlook 邮箱，但根项目已存在 `account_type == "imap"` 分支。

因此建议：
- 开放 API 仍允许对 `account_type == "imap"` 的账号调用
- 列表读取时复用 `get_emails_imap_generic()`
- 详情读取时复用 `get_email_detail_imap_generic()`
- `preferred_method` 返回 `imap_generic`

这样与 PRD 的“本地化部署邮件读取服务”目标更一致，也不把开放接口写死为仅支持 Outlook OAuth

---

## 10. 验证码与验证链接提取细节

### 10.1 当前提取器能力

`outlook_web/services/verification_extractor.py` 已具备：

- `smart_extract_verification_code()`
- `fallback_extract_verification_code()`
- `extract_links()`
- `extract_email_text()`
- `extract_verification_info()`

### 10.2 新增参数化入口

新增：

```python
def extract_verification_info_with_options(
    email: Dict[str, Any],
    *,
    code_regex: str | None = None,
    code_length: str | None = None,
    code_source: str = "all",
    prefer_link_keywords: list[str] | None = None,
) -> Dict[str, Any]:
```

### 10.3 `code_source` 实现

| 值 | 取值内容 |
|---|---|
| `subject` | 仅主题 |
| `content` | 仅纯文本正文 |
| `html` | 仅 HTML 内容 |
| `all` | 主题 + 纯文本 + HTML |

伪码：

```python
subject = email.get("subject", "")
content = extract_email_text(email)
html_content = email.get("body_html") or email.get("html_content") or ""

if code_source == "subject":
    source_text = subject
elif code_source == "content":
    source_text = content
elif code_source == "html":
    source_text = html_content
else:
    source_text = f"{subject} {content} {html_content}".strip()
```

### 10.4 `code_regex` 实现

若传入 `code_regex`：
- 先 `re.compile(code_regex)`
- 编译失败抛 `InvalidParamError("code_regex 参数无效")`
- 编译成功后直接用于优先提取

### 10.5 `code_length` 实现

格式示例：`4-8`、`6-6`

实现：

```python
m = re.match(r"^(\d+)-(\d+)$", code_length)
if not m:
    raise InvalidParamError("code_length 参数无效")
min_len = int(m.group(1))
max_len = int(m.group(2))
if min_len > max_len:
    raise InvalidParamError("code_length 参数无效")
pattern = rf"\b\d{{{min_len},{max_len}}}\b"
```

### 10.6 验证链接优先级实现

默认优先关键词：

```python
DEFAULT_LINK_KEYWORDS = [
    "verify",
    "confirmation",
    "confirm",
    "activate",
    "validation",
]
```

算法：
1. 提取全部链接
2. 遍历关键词
3. 返回第一个包含关键词的链接
4. 若无命中，返回 `links[0]`
5. 若无链接，抛 `VerificationLinkNotFoundError`

---

## 11. 统一响应与错误码映射

### 11.1 成功响应

```python
{
    "success": True,
    "code": "OK",
    "message": "success",
    "data": {...},
}
```

### 11.2 失败响应

```python
{
    "success": False,
    "code": "ACCOUNT_NOT_FOUND",
    "message": "邮箱账号不存在",
    "data": None,
}
```

### 11.3 自定义异常建议

建议在 `services/external_api.py` 中定义轻量异常：

```python
class ExternalApiError(Exception):
    code = "INTERNAL_ERROR"
    status = 500

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
```

### 11.4 错误码与 HTTP 映射

| code | HTTP | 触发条件 |
|---|---|---|
| `UNAUTHORIZED` | 401 | 缺少/错误 API Key |
| `API_KEY_NOT_CONFIGURED` | 403 | 系统未配置开放 API Key |
| `INVALID_PARAM` | 400 | 参数校验失败 |
| `ACCOUNT_NOT_FOUND` | 404 | 账号不存在 |
| `MAIL_NOT_FOUND` | 404 | 无匹配邮件 |
| `VERIFICATION_CODE_NOT_FOUND` | 404 | 邮件存在但无验证码 |
| `VERIFICATION_LINK_NOT_FOUND` | 404 | 邮件存在但无验证链接 |
| `PROXY_ERROR` | 502 | Graph 代理连接失败 |
| `UPSTREAM_READ_FAILED` | 502 | Graph/IMAP 全失败 |
| `INTERNAL_ERROR` | 500 | 未分类异常 |

---

## 12. 系统自检接口实现细节

### 12.1 `api_external_health()`

文件：`outlook_web/controllers/system.py`

目标：
- API Key 鉴权后返回轻量服务健康信息
- 不暴露管理员级详细调度器状态

建议实现：

```python
@api_key_required
def api_external_health():
    conn = create_sqlite_connection()
    try:
        db_ok = True
        try:
            conn.execute("SELECT 1").fetchone()
        except Exception:
            db_ok = False

        return jsonify({
            "success": True,
            "code": "OK",
            "message": "success",
            "data": {
                "status": "ok" if db_ok else "degraded",
                "service": "outlook-email-plus",
                "server_time_utc": utcnow().isoformat() + "Z",
                "database": "ok" if db_ok else "error",
            },
        })
    finally:
        conn.close()
```

### 12.2 `api_external_capabilities()`

返回固定能力列表：

```python
FEATURES = [
    "message_list",
    "message_detail",
    "raw_content",
    "verification_code",
    "verification_link",
    "wait_message",
]
```

### 12.3 `api_external_account_status()`

实现：
1. 校验 `email`
2. 查询 `accounts_repo.get_account_by_email(email)`
3. 若不存在，返回 `ACCOUNT_NOT_FOUND`
4. 存在则返回：
   - `exists`
   - `account_type`
   - `provider`
   - `group_id`
   - `last_refresh_at`
   - `preferred_method`
   - `can_read=True`

注意：
- 不在该接口中真正拉信
- 该接口是自检接口，不是链路测试接口

---

## 13. 前端设置页改造细节

### 13.1 `templates/index.html`

在系统设置页新增区块：

- `externalApiKey`：密码输入框
- `externalApiKeyHint`：显示“已配置/未配置”与脱敏值
- `generateExternalApiKeyBtn`：生成随机 Key

### 13.2 `static/js/main.js`

#### 13.2.1 `loadSettings()`

在现有 settings 拉取成功后追加：

```javascript
const externalApiKeyInput = document.getElementById('externalApiKey');
const externalApiKeyHint = document.getElementById('externalApiKeyHint');
if (externalApiKeyInput) externalApiKeyInput.value = '';
if (externalApiKeyHint) {
  const masked = data.settings.external_api_key_masked || '';
  const isSet = !!data.settings.external_api_key_set;
  externalApiKeyHint.textContent = isSet ? `已配置：${masked}` : '未配置';
}
```

#### 13.2.2 `saveSettings()`

```javascript
const externalApiKey = document.getElementById('externalApiKey')?.value?.trim() || '';
settings.external_api_key = externalApiKey;
```

#### 13.2.3 随机生成按钮

```javascript
function generateExternalApiKey() {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  const value = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
  document.getElementById('externalApiKey').value = value;
}
```

---

## 14. 兼容性与回归保障

### 14.1 内部接口不变

以下接口不允许因开放接口改造而改变：

- `GET /api/emails/<email_addr>`
- `GET /api/email/<email_addr>/<message_id>`
- `GET /api/emails/<email_addr>/extract-verification`
- `GET /api/settings`
- `PUT /api/settings`

### 14.2 加密兼容策略

`external_api_key` 读取逻辑必须兼容：
- 新数据：加密值
- 历史手工写入：明文值
- 空值：未配置

### 14.3 回退链路不变

开放接口与内部接口应共享相同的 Graph/IMAP 回退策略，避免两套行为分叉。

---

## 15. 测试策略与测试用例

### 15.1 测试文件建议

| 文件 | 说明 |
|---|---|
| `tests/test_external_api.py` | 开放接口主测试 |
| `tests/test_settings_external_api_key.py` | 设置项与加密兼容测试 |
| `tests/test_verification_extractor_options.py` | 提取器参数化测试 |

### 15.2 鉴权测试

- 未传 `X-API-Key` → 401 `UNAUTHORIZED`
- 未配置 `external_api_key` → 403 `API_KEY_NOT_CONFIGURED`
- 错误 key → 401 `UNAUTHORIZED`
- 正确 key → 进入 controller

### 15.3 `messages` 接口测试

- 正常返回列表
- `folder=spam` → 400
- 账号不存在 → 404
- Graph 成功时 `method=Graph API`
- Graph 失败 IMAP 成功时返回成功
- Graph 代理错误时返回 502 `PROXY_ERROR`

### 15.4 `messages/latest` 测试

- 命中最新邮件
- 无邮件 → 404 `MAIL_NOT_FOUND`

### 15.5 `messages/{id}` / `raw` 测试

- 正常获取详情
- 缺失 email → 400
- message_id 无效 → 404/502（视底层行为映射）

### 15.6 `verification-code` 测试

- 默认 4-8 位数字提取成功
- `code_length=6-6` 生效
- `code_regex` 生效
- `code_regex` 非法 → 400
- 邮件存在但无验证码 → 404 `VERIFICATION_CODE_NOT_FOUND`

### 15.7 `verification-link` 测试

- 命中 `verify` 关键词链接
- 无关键词时回退首个外链
- 无链接 → 404 `VERIFICATION_LINK_NOT_FOUND`

### 15.8 `wait-message` 测试

- 第一轮命中直接返回
- 多轮轮询后命中
- 超时返回 404 `MAIL_NOT_FOUND`
- `timeout_seconds > 120` → 400

### 15.9 系统接口测试

- `health` 返回 `status/service/database/server_time_utc`
- `capabilities` 返回固定 feature 列表
- `account-status` 存在/不存在路径正确

---

## 16. 实施顺序建议

### 16.1 第一阶段：配置与鉴权

1. `db.py` 初始化 `external_api_key`
2. `repositories/settings.py` 增加读取/脱敏函数
3. `security/auth.py` 增加 `api_key_required`
4. `controllers/settings.py` 与设置页对接

### 16.2 第二阶段：Service 抽离

1. 新增 `services/external_api.py`
2. 抽出 `_read_emails_with_fallback()`
3. 抽出 `_read_email_detail_with_fallback()`
4. 增强 `verification_extractor.py`

### 16.3 第三阶段：开放路由与 controller

1. 注册 `/api/external/messages*`
2. 注册 `/api/external/verification-*`
3. 注册 `/api/external/health|capabilities|account-status`
4. 接入审计日志

### 16.4 第四阶段：测试与文档

1. 补充 `tests/test_external_api.py`
2. 对照 OpenAPI 做返回结构校验
3. 更新 README / API 文档示例

---

## 结论

本 TDD 的核心落点是：

- **把开放 API 做成一层薄而稳定的外壳**，底层仍复用现有内部邮件读取能力；
- **把验证码/链接提取从“页面能力”升级为“服务能力”**，并支持参数化配置；
- **把设置、鉴权、审计、健康检查一起落地**，让开放接口从第一版就具备可配置、可接入、可排查的完整闭环；
- **通过新增 `services/external_api.py` 控制复杂度**，避免继续把复杂逻辑塞回 controller。
