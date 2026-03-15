# Outlook Email Plus

个人自用的 Outlook 邮件管理与验证码提取工具，提供 Web 界面、多账号统一管理，并支持一组**受控的对外只读 API**（`/api/external/*`）。

适用场景：自用/小团队受控环境，用于管理自己的邮箱、读取邮件、提取验证码/验证链接、对接内部自动化脚本。**不建议直接公网裸露**。

## 核心能力（现状）

- **多邮箱统一管理**：批量导入、分组、标签、搜索、批量操作
- **多链路读信**：Microsoft Graph / IMAP（按账号类型与回退策略）
- **验证码/链接提取**：支持按来源（subject/body/html）、长度范围、正则等策略增强提取稳定性
- **定时任务**：Token 定时刷新、调度器心跳、Telegram 推送轮询、对外 API 异步探测轮询
- **Telegram 实时推送（可选）**：后台轮询新邮件并推送到 Telegram，支持 Message-ID 去重与“首次启用不轰炸”策略
- **临时邮箱（可选）**：对接 GPTMail 临时邮箱服务（生成/刷新/清理/拉取消息）
- **对外只读 API（可选）**：API Key 鉴权 + 公网模式守卫（IP 白名单、限流、高风险端点可禁用）
- **安全基线**：敏感数据加密存储、CSRF 防护、登录限速/锁定、审计日志、对外 API 访问审计

## 快速开始

### Docker（推荐）

GHCR：

```bash
docker pull ghcr.io/zeropointsix/outlook-email-plus:latest

docker run -d \
  --name outlook-email-plus \
  -p 5000:5000 \
  -v $(pwd)/data:/app/data \
  -e SECRET_KEY=your-secret-key-here \
  -e LOGIN_PASSWORD=your-login-password \
  ghcr.io/zeropointsix/outlook-email-plus:latest
```

Docker Hub（如已同步启用）：

```bash
docker pull guangshanshui/outlook-email-plus:latest
```

PowerShell：

```powershell
docker run -d `
  --name outlook-email-plus `
  -p 5000:5000 `
  -v ${PWD}/data:/app/data `
  -e SECRET_KEY=your-secret-key-here `
  -e LOGIN_PASSWORD=your-login-password `
  ghcr.io/zeropointsix/outlook-email-plus:latest
```

说明：

- 强烈建议将 `data/` 挂载为持久化目录（数据库与运行数据）
- `SECRET_KEY` 用于会话与敏感字段加密。**丢失后无法解密旧数据**，请妥善保存并保持稳定

### 本地运行

```bash
python -m venv .venv
pip install -r requirements.txt
python start.py
```

`start.py` 会在缺少 `.env` 时自动从 `.env.example` 复制，并在 `SECRET_KEY` 为空/占位符时自动生成。

## 配置说明

优先通过环境变量或 `.env` 配置（参考 `.env.example`）。常用配置如下：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `SECRET_KEY` | 必填：会话/加密密钥（务必备份） | 无 |
| `LOGIN_PASSWORD` | 登录密码（首次启动会哈希存储） | `admin123` |
| `HOST` | 监听地址 | `0.0.0.0` |
| `PORT` | 监听端口 | `5000` |
| `DATABASE_PATH` | SQLite 数据库路径 | `data/outlook_accounts.db` |
| `SCHEDULER_AUTOSTART` | 是否自动启动后台调度器 | `true` |
| `PROXY_FIX_ENABLED` | 是否启用 ProxyFix（反代部署才需要） | `false` |
| `TRUSTED_PROXIES` | 受信任代理列表（用于安全解析 `X-Forwarded-For`） | 空 |
| `GPTMAIL_BASE_URL` | GPTMail 临时邮箱服务地址 | `https://mail.chatgpt.org.uk` |
| `GPTMAIL_API_KEY` | GPTMail API Key | `gpt-test` |
| `OAUTH_CLIENT_ID` | OAuth 助手默认 client_id（可选覆盖） | 内置默认值 |
| `OAUTH_REDIRECT_URI` | OAuth 助手重定向地址（可选覆盖） | `http://localhost:8080` |

生成 `SECRET_KEY`：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## 账号接入与使用

1. 在 Web 页面中添加/导入账号（Outlook 或 IMAP）
2. Outlook 账号需要 `client_id` 与 `refresh_token`（可在设置中使用 OAuth 助手换取 Refresh Token）
3. 选择分组/账号后拉取邮件，或直接提取验证码/验证链接
4. 如需后台能力（定时刷新/Telegram 推送/异步 probe），保持调度器开启（`SCHEDULER_AUTOSTART=true`）

常见导入格式：

```text
user@outlook.com----password123----client_id----refresh_token
```

## 对外只读 API（`/api/external/*`）

对外 API 仅用于**受控环境**调用，统一使用 `X-API-Key` 请求头鉴权（不依赖登录态）。API Key 可在「设置」中配置：

- 兼容旧模式：单个 legacy key（`external_api_key`）
- 推荐模式：多 Key 管理（可启停/删除、可配置允许访问的邮箱白名单）

常用端点：

- `GET /api/external/health`：健康检查（含版本号）
- `GET /api/external/capabilities`：能力与受限端点说明
- `GET /api/external/account-status?email=...`：账号可读性/上游探测摘要
- `GET /api/external/messages?email=...&folder=inbox&skip=0&top=20`
- `GET /api/external/messages/latest?email=...`
- `GET /api/external/messages/<message_id>` / `.../<message_id>/raw`
- `GET /api/external/verification-code?email=...`
- `GET /api/external/verification-link?email=...`
- `GET /api/external/wait-message?email=...&timeout_seconds=30&poll_interval=5`
  - 同步模式：默认阻塞等待
  - 异步模式：`mode=async` 返回 `probe_id`（202），再轮询 `GET /api/external/probe/<probe_id>`

最小调用示例：

```bash
curl -H "X-API-Key: <your-key>" http://localhost:5000/api/external/health
```

### 公网模式守卫（强烈建议）

如果你确实要在更开放的网络环境使用对外 API，请至少：

1. 通过设置开启「公网模式」
2. 配置 **IP/CIDR 白名单**（非白名单将返回 403）
3. 配置 **按 IP 限流**（默认每分钟 60）
4. 视需要禁用高风险端点：`raw_content`、`wait_message`
5. 放在反向代理之后，并只在可信代理场景下启用 `PROXY_FIX_ENABLED=true`，同时设置 `TRUSTED_PROXIES`（否则不要信任 `X-Forwarded-For`）

## 开发与测试

```bash
python -m unittest discover -s tests -v
```

## 界面预览

![仪表盘](img/仪表盘.png)
![邮箱界面](img/邮箱界面.png)
![提取验证码](img/提取验证码.png)
![设置界面](img/设置界面.png)

## 技术栈

- Flask
- SQLite
- Microsoft Graph API / IMAP
- APScheduler
- 原生 JavaScript

## 许可证

MIT
