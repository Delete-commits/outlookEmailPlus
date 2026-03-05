# BUG-00007 Telegram 推送实测问题

关联功能: TODO-00007 / FD-00007

## BUG-TG-001: 轮询间隔 min/max 限制过严

**现象**: 前端 HTML `<input>` 的 `min=60 max=3600` 和后端校验 `< 60 → 400` 限制了用户设置更灵活的轮询间隔。

**影响**: 用户无法设置 < 60 秒（快速调试）或 > 3600 秒（低频推送）的间隔。

**建议修复**:
- 前端：`min=10 max=86400`
- 后端：同步放宽范围 `10 ≤ interval ≤ 86400`
- 默认值保持 600 秒

**状态**: 待修复

---

## BUG-TG-002: 推送启用账号视觉区分度不够

**现象**: 账号卡片上的 🔔 按钮仅通过 `.tg-push-active` 颜色高亮，在深色/浅色主题下不够明显。

**影响**: 用户难以快速辨别哪些账号开启了推送。

**建议修复**:
- 方案 A: 切换图标 🔕/🔔 + 颜色变化
- 方案 B: 添加小徽标/角标 (badge)
- 方案 C: 在账号卡片标题旁显示 "推送中" 标签

**状态**: 待修复

---

## BUG-TG-003: Graph API 调用缺少 proxy_url（已修复 ✅）

**现象**: `_fetch_new_emails_graph` 未传递 proxy_url，导致在需要代理的网络环境中 Graph API 请求超时。

**根因**:
1. `get_access_token` 函数名错误 → 应为 `get_access_token_graph`
2. `get_access_token_graph` 需要 `client_id` 参数，但 `get_telegram_push_accounts()` 的 SELECT 未包含该列
3. Graph API 请求 (`requests.get`) 和 Token 请求均未传递 `proxy_url`

**修复内容** (commit `4adb255`):
- 修正导入: `get_access_token` → `get_access_token_graph`
- SELECT 增加 `client_id` 列
- LEFT JOIN `groups` 表获取 `proxy_url`
- 传递 `proxy_url` 到 `get_access_token_graph()` 和 `requests.get(proxies=...)`

**状态**: ✅ 已修复

---

## BUG-TG-004: 未配置代理时 Outlook 账号推送全部失败

**现象**: 在需要代理才能访问外网的环境中，Outlook 分组的 `proxy_url` 为空，导致所有 Graph API 调用报 SSL/超时错误。

**日志**:
```
SSLError: HTTPSConnectionPool(host='login.microsoftonline.com', port=443): Max retries exceeded
ConnectTimeoutError: Connection to login.microsoftonline.com timed out. (connect timeout=30)
```

**影响**: 所有 Outlook 账号的 Telegram 推送功能失效；IMAP 账号 (QQ) 同样超时。

**根因**: 用户环境配置问题 — 分组未设置代理 URL。代码已正确支持代理传递。

**建议修复**: 用户需在「分组管理」中为对应分组填写代理地址。

**状态**: 非代码问题 / 配置相关
