# Outlook 邮件管理工具｜Legacy 迁移到 Controllers 层 TODO（待办清单）

- 文档状态：草案
- 版本：V1.0
- 日期：2026-02-24
- 对齐 PRD：`docs/PRD/PRD-00003-Legacy代码拆分到Controllers层.md`
- 对齐 FD：`docs/FD/Outlook邮件管理工具-Legacy迁移到Controllers层FD.md`
- 对齐 TDD：`docs/TDD/Outlook邮件管理工具-Legacy迁移到Controllers层TDD.md`

---

## P0（必须完成）

### 阶段 0：文档与基线准备

#### 0.1 文档准备
- [x] PRD 文档已完成
- [x] FD 文档已完成
- [x] TDD 文档已完成
- [ ] 阅读并理解所有文档
- [ ] 明确验收标准和成功指标

#### 0.2 环境准备
- [ ] 确认开发环境正常（Python 3.x, Flask, SQLite）
- [ ] 确认所有依赖已安装：`pip install -r requirements.txt`
- [ ] 确认数据库正常：`data/outlook_accounts.db` 存在且可访问

#### 0.3 基线测试
- [ ] 运行所有现有测试：`python -m unittest discover -s tests -v`
- [ ] 确认所有测试通过（记录通过的测试数量）
- [ ] 手动验证核心功能正常：
  - [ ] 登录功能
  - [ ] 分组管理
  - [ ] 账号管理
  - [ ] 邮件读取
  - [ ] Token 刷新

#### 0.4 Git 准备
- [ ] 创建功能分支：`git checkout -b feature/migrate-to-controllers`
- [ ] 确认当前分支干净：`git status`
- [ ] 记录当前 commit hash（用于回滚）

---

### 阶段 1：基础模块迁移（低复杂度，无依赖）

**目标：** 迁移 groups, tags, settings, system, audit, pages 模块（共 19 个路由）

**预计时间：** 2-3 天

#### 1.1 创建 Controllers 目录结构

- [ ] 创建 `outlook_web/controllers/` 目录
- [ ] 创建 `outlook_web/controllers/__init__.py` 文件
- [ ] 在 `__init__.py` 中添加模块导出（如果需要）

#### 1.2 迁移 Groups 模块（6 个路由）

**文件：** `outlook_web/controllers/groups.py`

- [ ] 创建 `controllers/groups.py` 文件
- [ ] 从 `legacy.py` 提取以下函数：
  - [ ] `api_get_groups()` - 获取所有分组
  - [ ] `api_get_group(group_id)` - 获取单个分组
  - [ ] `api_add_group()` - 添加分组
  - [ ] `api_update_group(group_id)` - 更新分组
  - [ ] `api_delete_group(group_id)` - 删除分组
  - [ ] `api_export_group(group_id)` - 导出分组账号
- [ ] 调整导入语句：
  - [ ] 导入 `flask` 相关模块
  - [ ] 导入 `outlook_web.security.auth`
  - [ ] 导入 `outlook_web.repositories.groups`
  - [ ] 导入 `outlook_web.errors`
- [ ] 更新 `routes/groups.py`：
  - [ ] 移除 `impl` 参数
  - [ ] 导入 `controllers.groups`
  - [ ] 更新所有路由注册
- [ ] 更新 `app.py`：
  - [ ] 移除 `groups.ueprint(impl=legacy)`
  - [ ] 改为 `groups.create_blueprint()`
- [ ] 测试验证：
  - [ ] 运行单元测试：`python -m unittest tests.test_smoke_contract -v`
  - [ ] 手动测试所有 6 个 API：
    - [ ] GET /api/groups
    - [ ] GET /api/groups/<id>
    - [ ] POST /api/groups
    - [ ] PUT /api/groups/<id>
    - [ ] DELETE /api/groups/<id>
    - [ ] GET /api/groups/<id>/export
- [ ] 提交 Git：`git commit -m "feat: 迁移 groups 模块到 controllers 层"`

#### 1.3 迁移 Tags 模块（4 个路由）

**文件：** `outlook_web/controllers/tags.py`

- [ ] 创建 `controllers/tags.py` 文件
- [ ] 从 `legacy.py` 提取以下函数：
  - [ ] `api_get_tags()` - 获取所有标签
  - [ ] `api_add_tag()` - 添加标签
  - [ ] `api_delete_tag(tag_id)` - 删除标签
  - [ ] `api_batch_manage_tags()` - 批量管理标签
- [ ] 调整导入语句
- [ ] 更新 `routes/tags.py`
- [ ] 更新 `app.py`
- [ ] 测试验证：
  - [ ] 运行单元测试
  - [ ] 手动测试所有 4 个 API
- [ ] 提交 Git：`git commit -m "feat: 迁移 tags 模块到 controllers 层"`

#### 1.4 迁移 Settings 模块（3 个路由）

**文件：** `outlook_web/controllers/settings.py`

- [ ] 创建 `controllers/settings.py` 文件
- [ ] 从 `legacy.py` 提取以下函数：
  - [ ] `api_get_settings()` - 获取系统设置
  - [ ] `api_update_settings()` - 更新系统设置
  - [ ] `api_validate_cron()` - 验证 Cron 表达式
- [ ] 调整导入语句
- [ ] 更新 `routes/settings.py`
- [ ] 更新 `app.py`
- [ ] 测试验证：
  - [ ] 运行单元测试
  - [ ] 手动测试所有 3 个 API
- [ ] 提交 Git：`git commit -m "feat: 迁移 settings 模块到 controllers 层"`

#### 1.5 迁移 System 模块（3 个路由）

**文件：** `outlook_web/controllers/system.py`

- [ ] 创建 `controllers/system.py` 文件
- [ ] 从 `legacy.py` 提取以下函数：
  - [ ] `api_health_check()` - 健康检查
  - [ ] `api_get_diagnostics()` - 获取诊断信息
  - [ ] `api_get_upgrade_status()` - 获取升级状态
- [ ] 调整导入语句
- [ ] 更新 `routes/system.py`
- [ ] 更新 `app.py`
- [ ] 测试验证：
  - [ ] 运行单元测试
  - [ ] 手动测试所有 3 个 API
- [ ] 提交 Git：`git commit -m "feat: 迁移 system 模块到 controllers 层"`

#### 1.6 迁移 Audit 模块（1 个路由）

**文件：** `outlook_web/controllers/audit.py`

- [ ] 创建 `controllers/audit.py` 文件
- [ ] 从 `legacy.py` 提取以下函数：
  - [ ] `api_get_audit_logs()` - 获取审计日志
- [ ] 调整导入语句
- [ ] 更新 `routes/audit.py`
- [ ] 更新 `app.py`
- [ ] 测试验证：
  - [ ] 运行单元测试
  - [ ] 手动测试 API
- [ ] 提交 Git：`git commit -m "feat: 迁移 audit 模块到 controllers 层"`

#### 1.7 迁移 Pages 模块（3 个路由）

**文件：** `outlook_web/controllers/pages.py`

- [ ] 创建 `controllers/pages.py` 文件
- [ ] 从 `legacy.py` 提取以下函数：
  - [ ] `login()` - 登录页面
  - [ ] `logout()` - 登出
  - [ ] `index()` - 首页
- [ ] 调整导入语句
- [ ] 更新 `routes/pages.py`
- [ ] 更新 `app.py`
- [ ] 测试验证：
  - [ ] 运行单元测试
  - [ ] 手动测试所有 3 个页面
- [ ] 提交 Git：`git commit -m "feat: 迁移 pages 模块到 controllers 层"`

#### 1.8 阶段 1 验收

- [ ] 运行所有测试：`python -m unittest discover -s tests -v`
- [ ] 确认所有测试通过
- [ ] 手动回归测试：
  - [ ] 登录功能正常
  - [ ] 分组 CRUD 正常
  - [ ] 标签 CRUD 正常
  - [ ] 系统设置正常
  - [ ] 审计日志正常
- [ ] 性能测试：
  - [ ] 响应时间无明显增加
  - [ ] 内存使用无明显增加
- [ ] 代码审查：
  - [ ] 代码风格一致
  - [ ] 无重复代码
  - [ ] 注释清晰
- [ ] 合并到主分支（可选）：`git merge feature/migrate-to-controllers`

---

### 阶段 2：独立功能模块迁移

**目标：** 迁移 temp_emails, oauth, scheduler 模块（共 6 个路由）

**预计时间：** 1-2 天

#### 2.1 迁移 Temp Emails 模块（3 个路由）

**文件：** `outlook_web/controllers/temp_emails.py`

- [ ] 创建 `controllers/temp_emails.py` 文件
- [ ] 从 `legacy.py` 提取以下函数：
  - [ ] `api_get_temp_emails()` - 获取临时邮箱列表
  - [ ] `api_generate_temp_email()` - 生成临时邮箱
  - [ ] `api_get_temp_email_messages(email_id)` - 获取临时邮箱消息
- [ ] 调整导入语句
- [ ] 更新 `routes/temp_emails.py`
- [ ] 更新 `app.py`
- [ ] 测试验证：
  - [ ] 运行单元测试
  - [ ] 手动测试所有 3 个 API
- [ ] 提交 Git：`git commit -m "feat: 迁移 temp_emails 模块到 controllers 层"`

#### 2.2 迁移 OAuth 模块（2 个路由）

**文件：** `outlook_web/controllers/oauth.py`

- [ ] 创建 `controllers/oauth.py` 文件
- [ ] 从 `legacy.py` 提取以下函数：
  - [ ] `api_get_oauth_auth_url()` - 获取 OAuth 授权 URL
  - [ ] `api_exchange_oauth_token()` - 交换 OAuth Token
- [ ] 调整导入语句
- [ ] 更新 `routes/oauth.py`
- [ ] 更新 `app.py`
- [ ] 测试验证：
  - [ ] 运行单元测试
  - [ ] 手动测试 OAuth 流程
- [ ] 提交 Git：`git commit -m "feat: 迁移 oauth 模块到 controllers 层"`

#### 2.3 迁移 Scheduler 模块（1 个路由）

**文件：** `outlook_web/controllers/scheduler.py`

- [ ] 创建 `controllers/scheduler.py` 文件
- [ ] 从 `legacy.py` 提取以下函数：
  - [ ] `api_get_scheduler_status()` - 获取调度器状态
- [ ] 调整导入语句
- [ ] 更新 `routes/scheduler.py`
- [ ] 更新 `app.py`
- [ ] 测试验证：
  - [ ] 运行单元测试
  - [ ] 手动测试 API
- [ ] 提交 Git：`git commit -m "feat: 迁移 scheduler 模块到 controllers 层"`

#### 2.4 阶段 2 验收

- [ ] 运行所有测试：`python -m unittest discover -s tests -v`
- [ ] 确认所有测试通过
- [ ] 手动回归测试：
  - [ ] 临时邮箱功能正常
  - [ ] OAuth 授权流程正常
  - [ ] 调度器状态查询正常
- [ ] 性能测试无异常
- [ ] 代码审查通过

---

（文档未完，待续...）
### 阶段 3：核心复杂模块迁移

**目标：** 迁移 emails, accounts 模块（共 24 个路由）

**预计时间：** 3-4 天

#### 3.1 迁移 Emails 模块（4 个路由）

**文件：** `outlook_web/controllers/emails.py`

- [ ] 创建 `controllers/emails.py` 文件
- [ ] 从 `legacy.py` 提取以下函数：
  - [ ] `api_get_emails(email_addr)` - 获取邮件列表
  - [ ] `api_get_email_detail(email_addr, message_id)` - 获取邮件详情
  - [ ] `api_delete_emails()` - 删除邮件
  - [ ] `api_extract_verification(email_addr)` - 提取验证码
- [ ] 调整导入语句：
  - [ ] 导入 `outlook_web.services.graph`
  - [ ] 导入 `outlook_web.services.imap`
  - [ ] 导入 `outlook_web.repositories.accounts`
- [ ] 确保回退机制正常（Graph API → IMAP）
- [ ] 更新 `routes/emails.py`
- [ ] 更新 `app.py`
- [ ] 测试验证：
  - [ ] 运行单元测试
  - [ ] 手动测试所有 4 个 API
  - [ ] 测试 Graph API 成功场景
  - [ ] 测试 IMAP 回退场景
  - [ ] 测试代理配置
- [ ] 提交 Git：`git commit -m "feat: 迁移 emails 模块到 controllers 层"`

#### 3.2 迁移 Accounts 模块（20 个路由）

**文件：** `outlook_web/controllers/accounts.py`

**注意：** 这是最复杂的模块，建议分批迁移

##### 3.2.1 基础 CRUD（5 个路由）

- [ ] 创建 `controllers/accounts.py` 文件
- [ ] 从 `legacy.py` 提取以下函数：
  - [ ] `api_get_accounts()` - 获取账号列表
  - [ ] `api_get_account(account_id)` - 获取单个账号
  - [ ] `api_add_account()` - 添加账号
  - [ ] `api_update_account(account_id)` - 更新账号
  - [ ] `api_delete_account(account_id)` - 删除账号
- [ ] 调整导入语句
- [ ] 确保数据脱敏正常（client_id, refresh_token）
- [ ] 测试验证：
  - [ ] 运行单元测试
  - [ ] 手动测试所有 5 个 API
  - [ ] 验证数据脱敏

##### 3.2.2 批量操作（4 个路由）

- [ ] 从 `legacy.py` 提取以下函数：
  - [ ] `api_delete_account_by_email(email_addr)` - 按邮箱删除账号
  - [ ] `api_batch_delete_accounts()` - 批量删除账号
  - [ ] `api_batch_update_account_group()` - 批量更新分组
  - [ ] `api_search_accounts()` - 搜索账号
- [ ] 测试验证：
  - [ ] 运行单元测试
  - [ ] 手动测试所有 4 个 API
  - [ ] 测试批量操作性能

##### 3.2.3 导出功能（3 个路由）

- [ ] 从 `legacy.py` 提取以下函数：
  - [ ] `api_export_all_accounts()` - 导出所有账号
  - [ ] `api_export_selected_accounts()` - 导出选中账号
  - [ ] `api_generate_export_verify_token()` - 生成导出验证 Token
- [ ] 确保导出验证机制正常
- [ ] 测试验证：
  - [ ] 运行单元测试
  - [ ] 手动测试所有 3 个 API
  - [ ] 测试导出验证流程

##### 3.2.4 Token 刷新（8 个路由）

- [ ] 从 `legacy.py` 提取以下函数：
  - [ ] `api_refresh_account(account_id)` - 刷新单个账号
  - [ ] `api_refresh_all_accounts()` - 刷新所有账号
  - [ ] `api_retry_refresh_account(account_id)` - 重试刷新账号
  - [ ] `api_refresh_failed_accounts()` - 刷新失败账号
  - [ ] `api_trigger_scheduled_refresh()` - 触发定时刷新
  - [ ] `api_get_refresh_logs()` - 获取刷新日志
  - [ ] `api_get_account_refresh_logs(account_id)` - 获取账号刷新日志
  - [ ] `api_get_refresh_stats()` - 获取刷新统计
- [ ] 确保刷新机制正常
- [ ] 测试验证：
  - [ ] 运行单元测试
  - [ ] 手动测试所有 8 个 API
  - [ ] 测试刷新流程
  - [ ] 测试刷新日志

##### 3.2.5 更新 Routes 和 App

- [ ] 更新 `routes/accounts.py`
- [ ] 更新 `app.py`
- [ ] 提交 Git：`git commit -m "feat: 迁移 accounts 模块到 controllers 层"`

#### 3.3 阶段 3 验收

- [ ] 运行所有测试：`python -m unittest discover -s tests -v`
- [ ] 确认所有测试通过
- [ ] 手动回归测试：
  - [ ] 邮件读取功能正常
  - [ ] 邮件删除功能正常
  - [ ] 验证码提取功能正常
  - [ ] 账号 CRUD 功能正常
  - [ ] 批量操作功能正常
  - [ ] 导出功能正常
  - [ ] Token 刷新功能正常
  - [ ] 刷新日志功能正常
- [ ] 性能测试：
  - [ ] 邮件读取响应时间 < 2 秒
  - [ ] 账号列表响应时间 < 500ms
  - [ ] 批量操作响应时间 < 1 秒
- [ ] 代码审查通过

---

### 阶段 4：清理和优化

**目标：** 删除 legacy.py，迁移工具函数和中间件

**预计时间：** 1 天

#### 4.1 验证所有路由已迁移

- [ ] 检查 `legacy.py` 中是否还有 `api_*` 函数
- [ ] 确认所有 54 个路由都已迁移到 controllers/
- [ ] 确认所有 routes/ 文件都已更新
- [ ] 确认 app.py 中所有 Blueprint 注册都已更新

#### 4.2 迁移工具函数（可选）

**目标：** 将 legacy.py 中的工具函数迁移到 utils/

- [ ] 创建 `outlook_web/utils/` 目录
- [ ] 创建 `utils/__init__.py`
- [ ] 迁移以下工具函数：
  - [ ] `sanitize_input()` → `utils/sanitize.py`
  - [ ] `decode_header_value()` → `utils/sanitize.py`
  - [ ] `get_email_body()` → `utils/email_parser.py`
  - [ ] `parse_account_string()` → `utils/email_parser.py`
  - [ ] `utcnow()` → `utils/datetime.py`
  - [ ] `build_proxies()` → `utils/proxy.py`
- [ ] 更新所有引用这些函数的地方
- [ ] 测试验证
- [ ] 提交 Git：`git commit -m "refactor: 迁移工具函数到 utils 模块"`

#### 4.3 迁移中间件（可选）

**目标：** 将 legacy.py 中的中间件迁移到 middleware/

- [ ] 创建 `outlook_web/middleware/` 目录
- [ ] 创建 `middleware/__init__.py`
- [ ] 迁移以下中间件函数：
  - [ ] `ensure_trace_id()` → `middleware/trace.py`
  - [ ] `attach_trace_id_and_normalize_errors()` → `middleware/trace.py`
  - [ ] `handle_http_exception()` → `middleware/error_handler.py`
  - [ ] `handle_exception()` → `middleware/error_handler.py`
- [ ] 更新 app.py 中的中间件注册
- [ ] 测试验证
- [ ] 提交 Git：`git commit -m "refactor: 迁移中间件到 middleware 模块"`

#### 4.4 删除 legacy.py

- [ ] 确认所有函数都已迁移
- [ ] 备份 legacy.py：`cp outlook_web/legacy.py outlook_web/legacy.py.bak`
- [ ] 删除 legacy.py：`rm outlook_web/legacy.py`
- [ ] 更新所有导入 legacy 的地方
- [ ] 运行所有测试
- [ ] 确认应用正常启动
- [ ] 提交 Git：`git commit -m "refactor: 删除 legacy.py"`

#### 4.5 更新文档

- [ ] 更新 `CLAUDE.md`：
  - [ ] 更新项目架构说明
  - [ ] 更新目录结构说明
- [ ] 更新 `docs/DEV/00002-前后端拆分-开发者指南.md`：
  - [ ] 更新开发指南
  - [ ] 更新新增 API 的推荐路径
- [ ] 更新 `README.md`（如果需要）
- [ ] 提交 Git：`git commit -m "docs: 更新文档"`

#### 4.6 阶段 4 验收

- [ ] 运行所有测试：`python -m unittest discover -s tests -v`
- [ ] 确认所有测试通过
- [ ] 手动回归测试所有功能
- [ ] 性能测试无异常
- [ ] 代码审查通过
- [ ] 文档审查通过

---

## P1（重要但不紧急）

### 优化和改进

#### 5.1 代码优化

- [ ] 检查是否有重复代码，提取公共函数
- [ ] 检查是否有过长的函数，拆分为小函数
- [ ] 检查是否有复杂的条件判断，简化逻辑
- [ ] 检查是否有魔法数字，提取为常量

#### 5.2 测试覆盖率提升

- [ ] 为每个 controller 编写单元测试
- [ ] 为关键功能编写集成测试
- [ ] 使用 coverage 工具检查测试覆盖率
- [ ] 目标：测试覆盖率 > 80%

#### 5.3 性能优化

- [ ] 使用 profiler 工具分析性能瓶颈
- [ ] 优化数据库查询（如果需要）
- [ ] 优化 API 响应时间（如果需要）
- [ ] 添加缓存（如果需要）

#### 5.4 文档完善

- [ ] 为每个 controller 添加详细的文档字符串
- [ ] 为每个函数添加参数说明和返回值说明
- [ ] 编写 API 文档（如果需要）
- [ ] 编写开发者指南（如果需要）

---

## P2（可选）

### 进一步改进

#### 6.1 引入类型注解

- [ ] 为所有函数添加类型注解
- [ ] 使用 mypy 进行类型检查
- [ ] 修复类型错误

#### 6.2 引入日志系统

- [ ] 使用 Python logging 模块
- [ ] 为关键操作添加日志
- [ ] 配置日志级别和输出格式

#### 6.3 引入监控和告警

- [ ] 集成 Sentry 或其他监控工具
- [ ] 配置错误告警
- [ ] 配置性能监控

---

## 验收标准

### 功能验收

- [ ] 所有 54 个 API 路由都已迁移到 controllers/
- [ ] legacy.py 已删除
- [ ] 所有功能手动测试通过
- [ ] 前端功能正常，无需修改

### 质量验收

- [ ] 所有单元测试通过
- [ ] 所有集成测试通过
- [ ] 代码审查通过
- [ ] 性能测试通过（响应时间 < 迁移前 110%）

### 文档验收

- [ ] CLAUDE.md 已更新
- [ ] 开发者指南已更新
- [ ] 迁移文档已归档

---

## 风险和注意事项

### 风险识别

1. **路由映射错误**
   - 风险：URL 路径或 HTTP 方法错误
   - 应对：充分测试，使用自动化测试

2. **参数解析错误**
   - 风险：参数类型或名称错误
   - 应对：保持函数签名一致，单元测试覆盖

3. **依赖关系错误**
   - 风险：循环依赖或导入错误
   - 应对：遵循依赖方向规则，先迁移无依赖模块

4. **性能下降**
   - 风险：响应时间增加
   - 应对：性能测试对比，优化瓶颈

5. **功能回归**
   - 风险：某些功能不正常
   - 应对：完整的回归测试

### 注意事项

1. **每个阶段完成后提交 Git**
   - 便于回滚
   - 便于代码审查

2. **保留 legacy.py 直到所有模块迁移完成**
   - 作为参考
   - 便于回滚

3. **充分测试**
   - 单元测试
   - 集成测试
   - 手动测试

4. **性能监控**
   - 对比迁移前后的响应时间
   - 对比迁移前后的内存使用

5. **文档同步更新**
   - 及时更新文档
   - 保持文档和代码一致

---

## 进度跟踪

### 总体进度

- [x] 阶段 0：文档与基线准备（100%）
- [x] 阶段 1：基础模块迁移（100%）
- [x] 阶段 2：独立功能模块迁移（100%）
- [x] 阶段 3：核心复杂模块迁移（100%）
- [ ] 阶段 4：清理和优化（0%）

### 模块迁移进度

- [x] groups（6/6 路由）✅
- [x] tags（4/4 路由）✅
- [x] settings（3/3 路由）✅
- [x] system（3/3 路由）✅
- [x] audit（1/1 路由）✅
- [x] pages（3/3 路由）✅
- [x] temp_emails（3/3 路由）✅
- [x] oauth（2/2 路由）✅
- [x] scheduler（1/1 路由）✅
- [x] emails（4/4 路由）✅
- [x] accounts（20/20 路由）✅

**总计：** 54/54 路由已迁移（100%）

---

## 参考资料

- [PRD-00003-Legacy代码拆分到Controllers层](../PRD/PRD-00003-Legacy代码拆分到Controllers层.md)
- [Outlook邮件管理工具-Legacy迁移到Controllers层FD](../FD/Outlook邮件管理工具-Legacy迁移到Controllers层FD.md)
- [Outlook邮件管理工具-Legacy迁移到Controllers层TDD](../TDD/Outlook邮件管理工具-Legacy迁移到Controllers层TDD.md)
- [00002-前后端拆分-开发者指南](../DEV/00002-前后端拆分-开发者指南.md)
- [CLAUDE.md](../../CLAUDE.md)

---

**文档版本：** v1.0
**最后更新：** 2026-02-24
**维护者：** 开发团队
