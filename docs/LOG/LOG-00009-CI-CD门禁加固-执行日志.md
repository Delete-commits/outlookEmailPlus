# LOG-00009｜CI/CD 门禁加固 — 执行日志

## 目标

- 解决当前 CI/CD “有流程但门禁不硬”的问题
- 降低坏代码进入镜像仓库与主分支的概率
- 补齐类型检查、覆盖率与安全扫描的实际执行链路

## 问题分析

### 1) Docker 发布未绑定质量门禁

- 现状：
  - Docker workflow 只要推送到 `main/master` 就会执行构建并推送镜像
  - 与 Python Tests / Code Quality workflow 没有依赖关系
- 风险：
  - 单元测试失败时，镜像仍可能被推送到 GHCR / Docker Hub

### 2) 安全扫描不阻断

- 现状：
  - Bandit 使用 `|| true` 吞掉退出码
  - 只输出 JSON，不上传 SARIF，也不作为失败门禁
- 风险：
  - 安全问题只会显示在日志中，不会阻止合并或发布

### 3) `mypy` 名义存在但未执行

- 现状：
  - Workflow 安装了 `mypy`
  - 但没有任何实际 `mypy` 步骤
- 风险：
  - 类型回归无法在 CI 中被发现

### 4) Sonar 无覆盖率输入

- 现状：
  - Sonar workflow 只安装依赖并扫描
  - 未生成 `coverage.xml`
  - `sonar-project.properties` 未声明 Python coverage report
- 风险：
  - Sonar 只能做静态分析，无法给出真实测试覆盖信号

### 5) 路径过滤过窄

- 现状：
  - `static/**`、`templates/**`、`pyproject.toml` 等变更在部分 workflow 下不会触发
- 风险：
  - 实际影响镜像内容或检查规则的改动，可能绕过对应流水线

## 本轮整改（2026-03-10）

### A. Python Tests

- 补充触发路径：
  - `pyproject.toml`
  - `templates/**`
  - `static/**`
- 将语法检查从仅入口文件升级为：
  - `compileall` 检查 `outlook_web/`、入口文件与 `tests/`
- 新增 coverage 执行：
  - `coverage run -m unittest discover -s tests -v`
  - `coverage xml`
  - `coverage report`
- 上传 `coverage.xml` 作为 artifact，便于后续排查

### B. Code Quality

- 质量检查范围收敛到真实项目代码，避免把 `.venv/`、示例目录等一起扫进去
- `black` / `isort` / `flake8` 统一针对：
  - `outlook_web`
  - `tests`
  - `web_outlook_app.py`
  - `outlook_mail_reader.py`
  - `start.py`
- 复杂度阻断首期仅覆盖：
  - `repositories/settings.py`
  - `services/external_api.py`
  - `controllers/system.py`
  - `web_outlook_app.py`
- 增加 `mypy` 实际执行，首期先覆盖核心模块：
  - `repositories/settings.py`
  - `services/external_api.py`
  - `controllers/system.py`
  - `web_outlook_app.py`
- 在 `pyproject.toml` 增加基础 mypy 配置：
  - `ignore_missing_imports = true`
  - `warn_unused_ignores = true`
  - `follow_imports = "skip"`
- 说明：
  - 当前仓库历史类型债较重，首期采用“核心模块 + skip imports”方式渐进接入
  - 暂不把 `graph.py`、`emails.py` 等类型债较重模块纳入阻断集合

### C. Security Scan

- Bandit 改为扫描主代码入口，而不是整个仓库
- 输出格式改为 `sarif`
- 新增 SARIF 上传到 GitHub Security
- 不再直接完全放行；改为：
  1. 先运行 Bandit 并保存退出码
  2. 始终上传 SARIF
  3. 额外执行高危门禁扫描
  4. 仅在高严重度问题出现时阻断 workflow
- 说明：
  - 当前仓库已有较多历史低/中危告警，首期先将高危问题设为阻断条件

### D. Docker Build Push

- 增加 `quality-gate` job
- `build-and-push` 必须 `needs: quality-gate`
- 发布前现在保证：
  - `black` / `isort` 格式门禁通过
  - `flake8` 语法与首批复杂度门禁通过
  - `mypy` 核心模块类型检查通过
  - `bandit -lll` 高危安全门禁通过
  - `python -m unittest discover -s tests -v` 通过
- 同时补充触发路径：
  - `pyproject.toml`
  - `static/**`

### E. Sonar

- Sonar workflow 在扫描前先执行：
  - `coverage run -m unittest discover -s tests -v`
  - `coverage xml`
- `sonar-project.properties` 增加：
  - `sonar.python.coverage.reportPaths=coverage.xml`

### F. 测试日志清理

- 修复以下测试文件中多个响应对象未及时关闭的问题：
  - `tests/test_ui_redesign_bugs.py`
  - `tests/test_ui_settings_external_api_key.py`
- 目标：
  - 清除 CI 中 `ResourceWarning: unclosed file` 噪音
  - 让测试日志更干净，便于定位真实失败原因

## 本轮尚未彻底解决的点

### 1) Docker 发布仍存在“检查重复执行”

- 当前做法：
  - 通过在 Docker workflow 内重复执行核心质量检查与测试来保证发布门禁
- 原因：
  - GitHub Actions 原生 `workflow_run` 不适合同时精确依赖多个独立 workflow 的成功结果
- 后续优化方向：
  - 进一步抽象为 reusable workflow 或单一主流水线

### 2) `mypy` 仍是“核心模块优先”，不是全仓强校验

- 当前策略是渐进式引入，避免一次性把类型债全部打爆
- 后续应逐步扩大到更多模块

### 3) Bandit 当前仅对高危问题阻断

- 低/中危问题会进入 SARIF 与日志，但不会在首期直接打断 CI
- 后续应结合告警治理逐步收紧到中危

## 建议验证步骤

```bash
python -m black --check outlook_web tests web_outlook_app.py outlook_mail_reader.py start.py
python -m isort --check-only --profile black outlook_web tests web_outlook_app.py outlook_mail_reader.py start.py
python -m flake8 outlook_web tests web_outlook_app.py outlook_mail_reader.py start.py --count --select=E9,F63,F7,F82 --show-source --statistics
python -m flake8 outlook_web/repositories/settings.py outlook_web/services/external_api.py outlook_web/controllers/system.py web_outlook_app.py --count --max-complexity=10 --max-line-length=127 --statistics
python -m mypy --config-file pyproject.toml outlook_web/repositories/settings.py outlook_web/services/external_api.py outlook_web/controllers/system.py web_outlook_app.py
python -m bandit -r outlook_web web_outlook_app.py outlook_mail_reader.py start.py -lll
python -m unittest discover -s tests -v
```

## 结论

本轮整改后，CI/CD 从“有工作流”提升到了“关键路径开始具备真实门禁”：

- 发布前至少会跑测试
- 安全扫描不再默默放行
- 类型检查开始进入 CI
- 覆盖率开始进入流水线

仍然建议后续继续推进：

1. 合并为单一主流水线或 reusable workflow
2. 扩大 mypy 覆盖范围
3. 完整接入 Sonar coverage report
