# TEST-00008｜对外验证码与邮件读取开放 API — 测试文档

- **文档编号**: TEST-00008
- **创建日期**: 2026-03-08
- **版本**: V1.0
- **状态**: 草案
- **对齐 PRD**: `docs/PRD/PRD-00008-对外验证码与邮件读取开放API.md`
- **对齐 FD**: `docs/FD/FD-00008-对外验证码与邮件读取开放API.md`
- **对齐 TDD**: `docs/TDD/TDD-00008-对外验证码与邮件读取开放API.md`
- **对齐 OpenAPI**: `docs/FD/OPENAPI-00008-对外验证码与邮件读取开放API.yaml`
- **建议测试文件**:
  - `tests/test_external_api.py`
  - `tests/test_settings_external_api_key.py`
  - `tests/test_verification_extractor_options.py`

---

## 目录

1. [测试概述](#1-测试概述)
2. [测试策略](#2-测试策略)
3. [测试环境配置](#3-测试环境配置)
4. [P0 — 开放接口鉴权测试](#4-p0--开放接口鉴权测试)
5. [P0 — 开放消息接口功能测试](#5-p0--开放消息接口功能测试)
6. [P0 — 验证码与验证链接接口功能测试](#6-p0--验证码与验证链接接口功能测试)
7. [P0 — 系统自检接口功能测试](#7-p0--系统自检接口功能测试)
8. [P0 — 回归测试（旧接口零回归）](#8-p0--回归测试旧接口零回归)
9. [P1 — 设置页与配置测试](#9-p1--设置页与配置测试)
10. [P1 — 提取器参数化与边界测试](#10-p1--提取器参数化与边界测试)
11. [P1 — 审计日志与可观测性测试](#11-p1--审计日志与可观测性测试)
12. [手动验收测试清单](#12-手动验收测试清单)
13. [测试数据准备](#13-测试数据准备)
14. [验收标准与门禁](#14-验收标准与门禁)

---

## 1. 测试概述

### 1.1 测试目标

本测试文档覆盖“对外验证码与邮件读取开放 API”功能的完整验证，重点确保：

1. **新接口功能正确性**
   - `/api/external/messages*` 系列接口可稳定返回邮件列表、详情和 RAW 内容
   - `/api/external/verification-code` 能正确提取验证码
   - `/api/external/verification-link` 能正确提取验证链接
   - `/api/external/wait-message` 能按超时与轮询参数正确工作
   - `/api/external/health`、`/api/external/capabilities`、`/api/external/account-status` 返回结构与 OpenAPI 一致

2. **安全与配置正确性**
   - `X-API-Key` 鉴权严格生效
   - 未配置 `external_api_key` 时开放接口不可用
   - `external_api_key` 在设置接口中可正确保存、脱敏展示、兼容明文与加密值

3. **现有功能零回归**
   - 旧的内部邮件接口仍然按原方式工作
   - 现有 settings 接口与设置页其他字段不受影响
   - 现有验证码提取接口 `GET /api/emails/<email_addr>/extract-verification` 不被破坏
   - Graph → IMAP(New) → IMAP(Old) 回退链路保持一致

### 1.2 测试范围

**包含：**
- 开放接口鉴权测试
- 开放接口功能测试
- 开放接口参数校验测试
- 开放接口错误码测试
- 设置与 API Key 配置测试
- 审计日志测试
- 旧接口回归测试
- 手动联调验收测试

**不包含：**
- 真实 Outlook/IMAP 外网连通性压测
- 生产代理环境稳定性压测
- 前端端到端自动化浏览器测试（可在后续补充）

### 1.3 测试分类

| 类型 | 工具 | 目标 |
|---|---|---|
| 单元测试 | `unittest` + `unittest.mock` | 提取器、鉴权装饰器、参数校验 |
| 集成测试 | Flask test client + 临时 SQLite DB | Controller / Route / Repository / Settings |
| 回归测试 | 现有测试套件 + 定向补测 | 旧接口、旧设置、旧验证码提取 |
| 手动测试 | 浏览器 + curl/Postman | 配置页、联调、部署自检 |

---

## 2. 测试策略

### 2.1 核心原则

1. **新接口与旧接口同时验证**：所有关键新功能上线前，必须带上对应旧接口回归测试。
2. **优先做控制面测试**：先验证鉴权、配置、参数校验，再验证业务提取链路。
3. **隔离外部网络依赖**：Graph、IMAP、时间等待统一通过 `mock` 处理，不依赖真实网络。
4. **返回结构与 OpenAPI 对齐**：测试中必须校验 `success/code/message/data` 四元结构。
5. **重点关注错误路径**：鉴权失败、账号不存在、无匹配邮件、无验证码、无链接、上游失败都要覆盖。

### 2.2 Mock 策略

| 被 Mock 对象 | 路径 | 用途 |
|---|---|---|
| `graph_service.get_emails_graph` | `outlook_web.controllers.emails.graph_service.get_emails_graph` 或 service 层路径 | 模拟 Graph 成功/失败 |
| `graph_service.get_email_detail_graph` | 同上 | 模拟详情读取 |
| `imap_service.get_emails_imap_with_server` | `outlook_web.controllers.emails.imap_service.get_emails_imap_with_server` 或 service 层路径 | 模拟 IMAP 回退成功/失败 |
| `imap_service.get_email_detail_imap` | 同上 | 模拟 IMAP 详情回退 |
| `get_emails_imap_generic` | `outlook_web.controllers.emails.get_emails_imap_generic` 或 service 层路径 | 模拟通用 IMAP 分支 |
| `get_email_detail_imap_generic` | 同上 | 模拟通用 IMAP 详情 |
| `time.sleep` | `outlook_web.services.external_api.time.sleep` | 测试 `wait-message` 时避免真实等待 |
| `log_audit` | `outlook_web.controllers.emails.log_audit` / `outlook_web.controllers.system.log_audit` | 校验审计调用 |

### 2.3 测试优先级定义

| 优先级 | 含义 |
|---|---|
| P0 | 上线前必须全部通过；关系到功能可用性和回归安全 |
| P1 | 首版建议覆盖；关系到边界处理和可维护性 |
| P2 | 可后续补充；偏手工体验和长尾场景 |

---

## 3. 测试环境配置

### 3.1 运行方式

```bash
# 运行开放接口专项测试
python -m unittest tests.test_external_api -v

# 运行设置相关测试
python -m unittest tests.test_settings_external_api_key -v

# 运行提取器参数化测试
python -m unittest tests.test_verification_extractor_options -v

# 运行全量测试（含回归）
python -m unittest discover -s tests -v
```

### 3.2 测试环境要求

- 使用临时 SQLite 数据库
- 使用 `create_app()` 创建 Flask app 实例
- 通过 `app.test_client()` 调用接口
- 所有外部邮件读取依赖均通过 mock 隔离

### 3.3 通用测试前置

建议每个测试类在 `setUp()` 中完成：

1. 创建临时 DB
2. 初始化 `settings` 表和 `accounts` 表基础数据
3. 写入一个测试账号，例如：`user@outlook.com`
4. 设置或清空 `external_api_key`
5. 创建 `test_client`

---

## 4. P0 — 开放接口鉴权测试

### TC-AUTH-01：未传 `X-API-Key`

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-AUTH-01 |
| **优先级** | P0 |
| **前置条件** | 系统已配置 `external_api_key=abc123` |
| **操作步骤** | 调用 `GET /api/external/health`，不带 Header |
| **预期结果** | 返回 `401`；JSON 中 `code=UNAUTHORIZED` |

### TC-AUTH-02：系统未配置 `external_api_key`

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-AUTH-02 |
| **优先级** | P0 |
| **前置条件** | `settings.external_api_key=''` |
| **操作步骤** | 携带任意 `X-API-Key` 调用 `GET /api/external/health` |
| **预期结果** | 返回 `403`；`code=API_KEY_NOT_CONFIGURED` |

### TC-AUTH-03：错误 API Key

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-AUTH-03 |
| **优先级** | P0 |
| **前置条件** | `external_api_key=abc123` |
| **操作步骤** | 携带 `X-API-Key: wrong-key` 调用开放接口 |
| **预期结果** | 返回 `401`；`code=UNAUTHORIZED` |

### TC-AUTH-04：正确 API Key 放行

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-AUTH-04 |
| **优先级** | P0 |
| **前置条件** | `external_api_key=abc123` |
| **操作步骤** | 携带 `X-API-Key: abc123` 调用 `GET /api/external/health` |
| **预期结果** | 返回 `200`；`success=true` |

---

## 5. P0 — 开放消息接口功能测试

### TC-MSG-01：获取邮件列表成功（Graph 成功）

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-MSG-01 |
| **优先级** | P0 |
| **Mock** | `get_emails_graph` 返回 2 封邮件 |
| **操作步骤** | 调用 `GET /api/external/messages?email=user@outlook.com` |
| **预期结果** | 返回 `200`；`data.emails` 长度为 2；响应结构符合 OpenAPI |

### TC-MSG-02：获取邮件列表成功（Graph 失败，IMAP New 成功）

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-MSG-02 |
| **优先级** | P0 |
| **Mock** | Graph 失败，`get_emails_imap_with_server(..., IMAP_SERVER_NEW)` 成功 |
| **预期结果** | 返回 `200`；`method=IMAP (New)` 或结果中能识别回退成功 |

### TC-MSG-03：账号不存在

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-MSG-03 |
| **优先级** | P0 |
| **操作步骤** | 调用 `GET /api/external/messages?email=missing@outlook.com` |
| **预期结果** | 返回 `404`；`code=ACCOUNT_NOT_FOUND` |

### TC-MSG-04：folder 参数非法

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-MSG-04 |
| **优先级** | P0 |
| **操作步骤** | 调用 `GET /api/external/messages?email=user@outlook.com&folder=spam` |
| **预期结果** | 返回 `400`；`code=INVALID_PARAM` |

### TC-MSG-05：top 参数越界

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-MSG-05 |
| **优先级** | P0 |
| **操作步骤** | `top=0` 或 `top=999` |
| **预期结果** | 返回 `400` 或被截断到有效值（以最终实现为准，但必须与 OpenAPI 保持一致） |

### TC-MSG-06：按 `from_contains` 过滤

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-MSG-06 |
| **优先级** | P0 |
| **Mock** | 返回多封不同发件人的邮件 |
| **操作步骤** | 调用 `GET /api/external/messages?...&from_contains=openai` |
| **预期结果** | 仅返回命中发件人关键字的邮件 |

### TC-MSG-07：按 `subject_contains` 过滤

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-MSG-07 |
| **优先级** | P0 |
| **预期结果** | 仅返回主题命中的邮件 |

### TC-MSG-08：按 `since_minutes` 过滤

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-MSG-08 |
| **优先级** | P0 |
| **Mock** | 返回新旧时间混合邮件 |
| **预期结果** | 仅返回时间窗口内邮件 |

### TC-MSG-09：获取最新匹配邮件成功

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-MSG-09 |
| **优先级** | P0 |
| **Mock** | 返回多封按时间可区分邮件 |
| **预期结果** | `/api/external/messages/latest` 返回最新一封 |

### TC-MSG-10：最新邮件不存在

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-MSG-10 |
| **优先级** | P0 |
| **预期结果** | 返回 `404`；`code=MAIL_NOT_FOUND` |

### TC-MSG-11：获取邮件详情成功（Graph 详情成功）

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-MSG-11 |
| **优先级** | P0 |
| **Mock** | `get_email_detail_graph` 返回完整正文 |
| **操作步骤** | 调用 `/api/external/messages/{message_id}?email=user@outlook.com` |
| **预期结果** | 返回 `content/html_content/raw_content` 等字段 |

### TC-MSG-12：获取 RAW 成功

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-MSG-12 |
| **优先级** | P0 |
| **预期结果** | `/api/external/messages/{message_id}/raw` 只返回 `raw_content` 主体数据 |

### TC-MSG-13：详情读取 Graph 失败后 IMAP 回退成功

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-MSG-13 |
| **优先级** | P0 |
| **预期结果** | 返回 `200`，并标识实际读取方式 |

### TC-MSG-14：上游全部失败

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-MSG-14 |
| **优先级** | P0 |
| **Mock** | Graph/IMAP 均失败 |
| **预期结果** | 返回 `502`；`code=UPSTREAM_READ_FAILED` |

### TC-MSG-15：代理错误短路

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-MSG-15 |
| **优先级** | P0 |
| **Mock** | Graph 返回 `ProxyError` |
| **预期结果** | 返回 `502`；`code=PROXY_ERROR`；不继续走 IMAP |

---

## 6. P0 — 验证码与验证链接接口功能测试

### TC-VER-01：默认规则提取验证码成功

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-VER-01 |
| **优先级** | P0 |
| **Mock** | 最新邮件正文包含 `Your code is 123456` |
| **操作步骤** | 调用 `/api/external/verification-code?email=user@outlook.com` |
| **预期结果** | 返回 `verification_code=123456` |

### TC-VER-02：`code_length=6-6` 生效

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-VER-02 |
| **优先级** | P0 |
| **Mock** | 邮件正文同时存在 4 位和 6 位数字 |
| **预期结果** | 只提取 6 位验证码 |

### TC-VER-03：`code_regex` 生效

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-VER-03 |
| **优先级** | P0 |
| **Mock** | 邮件正文为 `OTP: AB12CD` |
| **操作步骤** | 带 `code_regex=\b[A-Z0-9]{6}\b` |
| **预期结果** | 正确提取 `AB12CD` |

### TC-VER-04：`code_regex` 非法

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-VER-04 |
| **优先级** | P0 |
| **操作步骤** | 传非法正则 |
| **预期结果** | 返回 `400`；`code=INVALID_PARAM` |

### TC-VER-05：`code_source=subject` 只从主题提取

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-VER-05 |
| **优先级** | P0 |
| **Mock** | 主题中有验证码，正文中无验证码 |
| **预期结果** | 提取成功 |

### TC-VER-06：邮件存在但无验证码

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-VER-06 |
| **优先级** | P0 |
| **预期结果** | 返回 `404`；`code=VERIFICATION_CODE_NOT_FOUND` |

### TC-VER-07：提取验证链接成功（命中高优先级关键字）

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-VER-07 |
| **优先级** | P0 |
| **Mock** | 邮件中包含 `https://example.com/verify?token=abc` |
| **预期结果** | 返回该链接 |

### TC-VER-08：无高优先级关键字时回退首个链接

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-VER-08 |
| **优先级** | P0 |
| **Mock** | 邮件中只有普通链接 |
| **预期结果** | 返回首个有效链接 |

### TC-VER-09：邮件存在但无验证链接

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-VER-09 |
| **优先级** | P0 |
| **预期结果** | 返回 `404`；`code=VERIFICATION_LINK_NOT_FOUND` |

### TC-VER-10：等待新邮件第一轮即命中

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-VER-10 |
| **优先级** | P0 |
| **Mock** | 第一次轮询即返回邮件 |
| **预期结果** | `/api/external/wait-message` 立即返回 `200` |

### TC-VER-11：等待新邮件多轮后命中

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-VER-11 |
| **优先级** | P0 |
| **Mock** | 前两次为空，第三次返回邮件 |
| **预期结果** | 返回 `200`；`time.sleep` 被调用两次 |

### TC-VER-12：等待新邮件超时

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-VER-12 |
| **优先级** | P0 |
| **Mock** | 始终无邮件 |
| **预期结果** | 返回 `404`；`code=MAIL_NOT_FOUND` |

### TC-VER-13：`timeout_seconds` 越界

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-VER-13 |
| **优先级** | P0 |
| **操作步骤** | `timeout_seconds=999` |
| **预期结果** | 返回 `400`；`code=INVALID_PARAM` |

---

## 7. P0 — 系统自检接口功能测试

### TC-SYS-01：`/api/external/health` 成功

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-SYS-01 |
| **优先级** | P0 |
| **预期结果** | 返回 `status/service/server_time_utc/database` |

### TC-SYS-02：`/api/external/capabilities` 成功

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-SYS-02 |
| **优先级** | P0 |
| **预期结果** | 返回固定 feature 列表；包含 `message_list`、`verification_code`、`verification_link` |

### TC-SYS-03：`/api/external/account-status` 成功

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-SYS-03 |
| **优先级** | P0 |
| **前置条件** | 测试账号存在 |
| **预期结果** | 返回 `exists=true` 与账号基本字段 |

### TC-SYS-04：`account-status` 账号不存在

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-SYS-04 |
| **优先级** | P0 |
| **预期结果** | 返回 `404`；`code=ACCOUNT_NOT_FOUND` |

---

## 8. P0 — 回归测试（旧接口零回归）

### TC-REG-01：旧邮件列表接口仍可用

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-REG-01 |
| **优先级** | P0 |
| **操作步骤** | 使用登录态调用 `GET /api/emails/<email_addr>` |
| **预期结果** | 返回结构与旧实现保持一致 |

### TC-REG-02：旧邮件详情接口仍可用

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-REG-02 |
| **优先级** | P0 |
| **操作步骤** | 使用登录态调用 `GET /api/email/<email_addr>/<message_id>` |
| **预期结果** | 返回旧结构，不因开放接口改造失败 |

### TC-REG-03：旧验证码提取接口仍可用

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-REG-03 |
| **优先级** | P0 |
| **操作步骤** | 使用登录态调用 `GET /api/emails/<email_addr>/extract-verification` |
| **预期结果** | 仍可提取验证码/链接 |

### TC-REG-04：设置接口旧字段不受影响

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-REG-04 |
| **优先级** | P0 |
| **操作步骤** | `GET /api/settings` |
| **预期结果** | `refresh_interval_days`、`gptmail_api_key`、Telegram 配置等旧字段行为不变 |

### TC-REG-05：设置保存旧字段不受影响

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-REG-05 |
| **优先级** | P0 |
| **操作步骤** | `PUT /api/settings` 只修改旧字段 |
| **预期结果** | 旧字段正常保存；不要求必须同时提交 `external_api_key` |

### TC-REG-06：Graph → IMAP 回退链不变

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-REG-06 |
| **优先级** | P0 |
| **Mock** | Graph 失败，IMAP 成功 |
| **预期结果** | 内部接口与开放接口均按同一回退策略返回 |

---

## 9. P1 — 设置页与配置测试

### TC-SET-01：`external_api_key` 保存成功

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-SET-01 |
| **优先级** | P1 |
| **操作步骤** | 登录后 `PUT /api/settings`，提交 `external_api_key=abc123` |
| **预期结果** | 返回成功；DB 中存在该值（建议加密） |

### TC-SET-02：`external_api_key` 脱敏返回

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-SET-02 |
| **优先级** | P1 |
| **操作步骤** | 登录后 `GET /api/settings` |
| **预期结果** | 返回 `external_api_key_set=true` 和 `external_api_key_masked`；不返回明文 |

### TC-SET-03：兼容历史明文值

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-SET-03 |
| **优先级** | P1 |
| **前置条件** | 手工向 DB 写入明文 `external_api_key` |
| **预期结果** | 读取仍正常，鉴权仍有效 |

### TC-SET-04：清空 API Key

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-SET-04 |
| **优先级** | P1 |
| **操作步骤** | `PUT /api/settings`，提交空字符串 |
| **预期结果** | 之后开放接口返回 `403 API_KEY_NOT_CONFIGURED` |

---

## 10. P1 — 提取器参数化与边界测试

### TC-EXT-01：`code_source=html` 仅从 HTML 提取

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-EXT-01 |
| **优先级** | P1 |
| **预期结果** | 只从 HTML 内容命中验证码 |

### TC-EXT-02：`code_length` 格式非法

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-EXT-02 |
| **优先级** | P1 |
| **输入** | `code_length=abc`、`8-4` |
| **预期结果** | 返回 `400 INVALID_PARAM` |

### TC-EXT-03：多个候选验证码时优先关键词邻近值

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-EXT-03 |
| **优先级** | P1 |
| **Mock** | 邮件中存在多个数字 |
| **预期结果** | 优先提取靠近 `code` / `OTP` 等关键词的值 |

### TC-EXT-04：多个链接时优先 `verify`/`confirm`

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-EXT-04 |
| **优先级** | P1 |
| **预期结果** | 优先返回高优先级链接 |

---

## 11. P1 — 审计日志与可观测性测试

### TC-AUD-01：开放接口成功调用写审计日志

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-AUD-01 |
| **优先级** | P1 |
| **操作步骤** | 成功调用任一开放接口 |
| **预期结果** | `audit_logs` 中新增一条 `action=external_api_access` 记录 |

### TC-AUD-02：开放接口失败调用也写审计日志

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-AUD-02 |
| **优先级** | P1 |
| **操作步骤** | 触发 `MAIL_NOT_FOUND` 或 `INVALID_PARAM` |
| **预期结果** | 仍有审计记录，且 details 中包含错误码 |

### TC-AUD-03：日志中不包含明文 API Key

| 属性 | 值 |
|---|---|
| **测试 ID** | TC-AUD-03 |
| **优先级** | P1 |
| **预期结果** | `audit_logs.details` 中不出现完整 API Key |

---

## 12. 手动验收测试清单

### 12.1 设置页验收

- 登录后台
- 进入系统设置
- 配置开放 API Key
- 保存后刷新页面
- 确认页面仅显示脱敏值，不显示明文

### 12.2 curl 联调验收

```bash
curl -H "X-API-Key: your-api-key" "http://localhost:5000/api/external/health"

curl -H "X-API-Key: your-api-key" "http://localhost:5000/api/external/messages?email=user@outlook.com"

curl -H "X-API-Key: your-api-key" "http://localhost:5000/api/external/verification-code?email=user@outlook.com&subject_contains=verify&since_minutes=10"
```

验收点：
- 能正确返回 JSON
- 错误码与 message 清晰
- OpenAPI 字段与实际响应一致

### 12.3 本地部署联调验收

- 部署实例
- 配置 API Key
- 通过 `/api/external/health` 检查服务状态
- 通过 `/api/external/account-status` 确认测试邮箱存在
- 发一封带验证码的测试邮件
- 通过 `/api/external/verification-code` 读取验证码

---

## 13. 测试数据准备

### 13.1 测试账号

| 邮箱 | 类型 | 用途 |
|---|---|---|
| `user@outlook.com` | outlook | 主流程测试 |
| `missing@outlook.com` | 不存在 | 404 测试 |
| `imap@example.com` | imap | 通用 IMAP 分支兼容测试 |

### 13.2 模拟邮件数据

#### 验证码邮件

```python
{
    "id": "msg-001",
    "subject": "Your verification code",
    "from": {"emailAddress": {"address": "noreply@example.com"}},
    "receivedDateTime": "2026-03-08T12:00:00Z",
    "bodyPreview": "Your code is 123456",
}
```

#### 验证链接邮件

```python
{
    "id": "msg-002",
    "subject": "Please verify your email",
    "from": {"emailAddress": {"address": "noreply@example.com"}},
    "receivedDateTime": "2026-03-08T12:01:00Z",
    "bodyPreview": "Click https://example.com/verify?token=abc",
}
```

---

## 14. 验收标准与门禁

### 14.1 上线前最低门禁

- 所有 P0 测试用例通过
- 旧接口回归测试全部通过
- OpenAPI 中定义的核心接口返回结构与实际一致
- 设置页中 API Key 脱敏展示正确
- `python -m unittest discover -s tests -v` 无新增回归失败

### 14.2 建议覆盖率目标

| 模块 | 覆盖率目标 |
|---|---|
| `outlook_web/services/external_api.py` | 85%+ |
| `outlook_web/security/auth.py` 新增部分 | 90%+ |
| `outlook_web/services/verification_extractor.py` 新增部分 | 85%+ |
| `outlook_web/controllers/emails.py` 新增开放接口部分 | 80%+ |

### 14.3 验收结论标准

满足以下条件视为可进入开发完成态：

1. 新开放接口功能可用
2. 旧接口无明显回归
3. 鉴权与配置链路闭环
4. 核心错误码与 OpenAPI 一致
5. 手动联调可完成“配置 → 健康检查 → 查邮件 → 取验证码/链接”全流程
