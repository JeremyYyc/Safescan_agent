# CI/CD 技术文档（P00）

## 1. 目标与范围

P00 的目标是在数据库迁移之前建立可靠的 GitHub CI/CD 基线。核心是 CI：任何代码进入共享分支前都必须经过自动化质量检查。CI 采用渐进式演进，后续每新增一个可测试模块、基础设施或风险边界，都必须同步增加对应测试、CI job 或门禁。CD 在 P00 只保留 Docker 镜像构建验证和可选的手动部署，不自动发布生产环境。

## 2. 触发规则

| 事件 | 目标 | 要求 |
|---|---|---|
| `push` 任意分支 | 快速反馈 | lint、测试、构建和安全检查 |
| Pull Request opened/synchronize/reopened | 合并门禁 | 完整 CI，required checks 全部通过 |
| merge 到 `main` | 合并后验证 | 再执行完整 CI，并生成可追溯构建产物 |
| tag/release | 发布候选 | 完整 CI + Docker 镜像构建；生产部署仍需手动批准 |

Merge commit 不能绕过 CI；`main` 必须启用 branch protection，要求 Pull Request、required status checks、禁止直接 push，并要求分支更新后重新检查。

## 3. 渐进式 CI 治理规则

每个新增或修改的技术能力都必须在同一个 Pull Request 中登记：

```text
能力/模块 → 风险 → 测试类型 → CI job → 是否 Required Check
→ 启用阶段 → 失败回退方案
```

Pull Request 必须说明是否新增数据库、外部服务、队列、模型、文件格式、API/schema、状态转换或权限边界，并列出对应测试。暂时无法自动化的检查必须有负责人、补齐期限和临时风险记录，不得永久使用 optional 或 `continue-on-error` 隐藏失败。

## 4. 分阶段 CI 路线

当前仓库仍使用 MySQL 8.0：现有 `docker-compose.yml`、`backend/.env.test` 和生产配置都没有 PostgreSQL。因此 PostgreSQL 集成测试不能在当前阶段作为 required check。

### P00-A：当前栈 CI 基线

在 PostgreSQL 引入前执行：

```text
前端 lint/build
→ 后端 import/lint/unit test
→ API contract test
→ MySQL integration test
→ Docker backend/frontend build
→ Compose smoke test
→ security/secret scan
```

P00-A 的 Required Checks 不包含 PostgreSQL。

### P00-B：数据库迁移完成

新建 PostgreSQL Docker service，完成现有业务表的离线迁移、数据校验和旧 API 回放。此阶段 PostgreSQL 测试可以作为独立的迁移验收 job，但在迁移完成前不作为主分支门禁。

### P00-C：PostgreSQL CI 门禁

PostgreSQL 已经进入 Docker Compose、环境配置、Repository 和测试夹具后，再将 `postgres-integration` 升级为 Required Check，并逐步移除 MySQL integration test。

## 5. 完整 CI 流程

```text
Checkout
  ↓
依赖安装与缓存
  ↓
前端 lint / build
  ↓
后端 compile/import / lint / unit test
  ↓
API contract test
  ↓
数据库 integration test（P00-A 为 MySQL；P00-C 为 PostgreSQL）
  ↓
Docker backend/frontend build
  ↓
Compose smoke test
  ↓
安全扫描与敏感信息扫描
  ↓
上传测试报告、覆盖率和镜像摘要
```

任一 required job 失败即阻止合并。外部模型调用默认 mock，CI 不依赖真实 DashScope/OpenAI key。

## 6. Job 设计

建议拆成以下 jobs：

- `frontend-quality`：`npm ci`、`npm run lint`、`npm run build`。
- `backend-quality`：Python 版本矩阵、导入检查、格式/lint、单元测试。
- `api-contract`：OpenAPI/DTO schema、错误格式、状态转换、幂等和权限测试。
- `database-integration`：P00-A 启动 MySQL service；P00-C 切换为 PostgreSQL service。不能在 PostgreSQL 尚未进入仓库前创建这个 required job。
- `docker-build`：构建 backend/frontend 镜像，校验 Compose 配置，不推送镜像。
- `compose-smoke`：启动 Docker Compose，检查 health endpoint、前端静态资源和后端基础接口。
- `security`：secret scan、依赖漏洞扫描、上传路径和配置检查。
- `migration-dry-run`：只在 migration 变更或 Pull Request 时执行，禁止真实数据和 `--apply`。

## 7. 运行环境与依赖

- CI 使用固定的 Python、Node.js 和 PostgreSQL major version，并与 Dockerfile/Compose 保持一致。
- 依赖使用 lockfile 或 requirements pin；缓存命中不能改变依赖解析结果。
- 测试数据库使用临时 PostgreSQL service，job 结束后销毁。
- 测试使用最小 fixture；禁止读取真实用户视频、数据库、生产密钥或线上对象存储。
- 允许配置 `DASHSCOPE_API_KEY` 的 mock provider，但默认不得因缺少真实 key 失败。

## 8. 渐进式 CI 能力登记表

| 阶段 | 新增 CI 能力 | 触发条件 | Required Check |
|---|---|---|---|
| P00-A | 前端/后端质量、API contract、MySQL integration、Docker、smoke、security | 每次 push/PR/merge | 是 |
| P00-B | PostgreSQL schema/migration dry-run、数据校验、回放 | migration/schema 变更 | 迁移 PR 必须通过 |
| P00-C | PostgreSQL integration，替代 MySQL integration | PostgreSQL 成为事实源 | 是 |
| P0 | Evidence/schema、workflow state、幂等、SSE、软删除/恢复、导出 | 对应代码或契约变更 | 是 |
| P0-RAG | ingestion、metadata、hybrid retrieval、citation、无答案/注入 | KB/RAG 变更 | 是 |
| P1/P2 | checkpoint/HITL、Property、Regulation、Device、Rental 评测 | 对应能力启用 | 是 |

每个阶段完成后更新本表和 workflow 配置；旧阶段 Required Checks 不得被新阶段静默删除。

## 9. CI 失败分类

| 类别 | 示例 | 处理 |
|---|---|---|
| 代码质量 | lint、格式、类型失败 | 修复后重新 push |
| 测试失败 | 单测、API、集成失败 | 禁止合并 |
| 环境失败 | Docker/依赖下载/服务启动失败 | 重跑一次；仍失败则修复 CI |
| 外部服务失败 | 真实模型或外部网站不可用 | CI 使用 mock，不允许成为 required check 的常态依赖 |
| 安全失败 | secret、严重漏洞、越权测试失败 | 禁止合并，需明确豁免记录 |

不允许通过 `continue-on-error` 隐藏 required job 失败。允许重试必须限制次数并保留失败日志。

## 10. P00 验收标准

- 任意分支 push 能触发 CI。
- Pull Request 能自动运行完整 CI 并显示 required checks。
- merge 到 `main` 后再次运行完整 CI。
- `main` 禁止绕过 required checks 直接合并。
- P00-A 阶段前后端 lint/build/test、API contract、MySQL integration、Docker build 和 smoke test 均有独立结果。
- P00-B 完成 PostgreSQL Docker service、schema、迁移脚本、数据校验和回放报告。
- P00-C 阶段 PostgreSQL integration 才升级为 required check，并替代 MySQL integration。
- CI 不依赖真实模型 key、生产数据库或真实用户数据。
- 失败时能看到 job、日志、测试报告和 request/build 信息。
- 能保留 coverage、测试报告、Docker build digest 等构建产物。

## 11. CD 边界

P00 不自动部署生产。CD 只做：

```text
CI 通过 → 构建不可变 Docker 镜像 → 生成 digest
→ 手动触发 test/staging 部署（可选）
```

数据库迁移必须单独使用 [迁移 Runbook](./11-migration-runbook.md)，CI 只能执行 dry-run 和校验，不能在 Pull Request 中连接生产数据库或执行真实迁移。P00-A 不得伪造 PostgreSQL 测试；P00-C 才使用 CI 临时 PostgreSQL service。

## 12. 待实现文件

正式落地时新增：

```text
.github/workflows/ci.yml
.github/workflows/post-merge.yml
.github/workflows/release.yml（可选）
.github/dependabot.yml（可选）
```

在创建 workflow 前必须先确认后端实际测试命令、Python 版本、Docker Compose 服务名和 CI 使用的 PostgreSQL 版本。
