# SafeScan P0 并行开发执行基线

> 版本：v1.0
> 状态：并行开发启动门禁
> 业务与接口依据：`PRD-NON-AGENT-MVP.zh-CN.md` 和 `backend/api/`

## 1. 适用原则

1. PRD 定义 P0 用户流程，API 文档定义状态机、权限和接口；实现不能自行改变已冻结规则。
2. 每个对话使用独立 branch + Git worktree，不允许多个对话在同一工作目录编辑。
3. 前端只调用对应 Portal BFF；BFF 不拥有业务表；领域服务拥有最终业务规则和授权判断。
4. P0 以完整主链路可运行优先，不预建动态 ACL、通用工作流或新的分布式基础设施。
5. 现有视频 Pipeline 是受保护内核；报告任务只增加 property/lease 外围适配，不改原分析语义。

## 2. 开工门禁与首次启动顺序

以下顺序是首次建立并行开发环境的唯一基线：

0. 先把本文件、文档索引和目标目录调整作为纯文档 PR 合入 `main`；不得和 Identity、Compose 或
   Gateway 代码混在同一提交。
1. 本地 fast-forward 到最新 `origin/main`，确认二者指向同一已通过 CI 的提交；从该精确提交创建
   并推送 `integration/p0-skeleton`。这个分支只作为集成目标，不在其工作区直接开发功能。
2. 从 `integration/p0-skeleton` 的同一初始提交创建 `refactor/p0-skeleton`，只接收 Compose、Gateway、
   环境变量、空服务/前端骨架、健康检查和 CI 变更。
3. `refactor/p0-skeleton` 先通过现有 `refactor/**` push CI、本地 Compose config/smoke 和文件范围
   检查，再以 PR 合入 `integration/p0-skeleton`。
4. 该基础设施 PR 必须扩展 GitHub Actions：push 到 `integration/**`，以及目标为
   `integration/p0-skeleton` 的 PR，都运行与 `main` PR 相同的必需检查。由于旧 base 尚无这个触发
   配置，第一份基础设施 PR 允许以成功的 head push CI 作为等价门禁；合入后不得继续使用此例外。
5. 在集成分支验证最小骨架后记录新的基线 SHA。A–G 所有功能 branch/worktree 必须从这个相同 SHA
   创建，不得从步骤 1 的空集成分支或各自不同的 `main` 提交创建。

进入步骤 5 前还必须满足：

- 当前未提交文件已逐项归属到一个任务；混合改动先拆分提交，不直接复制到多个 worktree。
- 基础设施骨架已固定 Compose 服务名/端口、Gateway 路由、两个 React 空壳、两个 BFF 空壳、健康
  检查，以及 PostgreSQL/Redis/MinIO。
- Markdown API 契约已冻结，并已固定 OpenAPI 快照、生成 client 和 Mock fixture 的目标路径；实际
  OpenAPI 由各 HTTP 服务任务实现，不阻塞它们开始并行。
- 12 名员工、最小房源和可注入时钟的 fixture 值、文件归属及预期命令名称已确定；实际 seed/时钟
  分别由 Identity、Property Leasing 任务实现，不要求基础设施分支提前伪造业务数据。

当前工作区已有未提交的 Identity、Compose、Gateway 和 schema 改动。开始并行前，负责人必须先
审查并分别移入 Identity 或基础设施任务；不得把整个脏工作区作为所有分支共同起点。尤其不得把
Identity 文件带入 `refactor/p0-skeleton`，也不得把基础设施共享文件带入 `feature/identity-p0`。

## 3. 并行任务与目录所有权

| 任务 | 建议分支 | 独占写目录 | 主要交付 |
|---|---|---|---|
| 基础设施 | `refactor/p0-skeleton` | `docker-compose.yml`、`.env.example`、`gateway/`、`.github/workflows/`、根级运行脚本 | 服务骨架、网络、健康检查、CI/E2E 入口 |
| A 员工前端 | `feature/staff-web` | `frontend/apps/staff-web/` | 登录、布局、房源、订单、维修、员工权限、报告入口 |
| B 租户前端 | `feature/tenant-web` | `frontend/apps/tenant-web/` | 注册登录、房源、联系、申请、合同、我的房子、维修、报告 |
| C Identity | `feature/identity-p0` | `backend/services/identity-access-service/` | 登录、12 人 seed、权限、客户阶段、删除/Tombstone |
| D Property Leasing | `feature/property-leasing-p0` | `backend/services/property-leasing-service/` | 房源、case、申请、合同、唯一租约、生命周期、账单只读 |
| E Portal BFF | `feature/portal-bffs-p0` | `backend/services/staff-portal-api/`、`backend/services/tenant-portal-api/` | 页面 DTO、聚合、脱敏、404 归一化、下游超时 |
| F Maintenance | `feature/maintenance-p0` | `backend/services/maintenance-service/` | 租客报修、分派、处理、删除 blocker |
| G Report migration | `feature/report-property-p0` | `backend/services/inspection-report-service/`；经批准后才改 `backend/app/` 报告适配点 | property/source lease 关联、持久 job、旧 Pipeline adapter |

共享目录规则：

- `backend/packages/safescan-common/` 只放 HTTP、auth、日志、DB 等横切技术代码，由基础设施负责人
  审核；禁止放 Lease/Application/Report 等业务 DTO 或状态枚举。
- `frontend/packages/` 只放无业务状态的 UI 基础组件和生成工具。两个 Portal 的页面模型分别由各自
  OpenAPI client 持有，不建立一个可写的前端业务全局模型。
- `docs/` 的业务契约变更必须先单独评审；实现 PR 只能同步文档描述，不能顺手改业务决定。
- 任务需要修改其他任务的独占目录时，先由目录 owner 接受一个小型依赖 PR；禁止跨目录大规模改动。

## 4. Worktree 与提交规则

基础设施合入并通过验证后，每个任务从记录的同一个 `integration/p0-skeleton` 基线 SHA 创建，例如：

```sh
git worktree add ../safescan-staff-web -b feature/staff-web integration/p0-skeleton
git worktree add ../safescan-tenant-web -b feature/tenant-web integration/p0-skeleton
```

- 一个 worktree 只绑定一个任务分支；不得通过复制目录共享未提交文件。
- `integration/p0-skeleton` 只允许首次创建时直接推送；此后所有变更必须通过 PR。基础设施分支必须
  从该集成分支的初始 SHA 创建，功能分支必须从基础设施合入后的新基线 SHA 创建。
- 提交按可验证用例拆分，推荐 `feat(identity): ...`、`feat(leasing): ...`、`test(contract): ...`。
- 禁止 force push、跨任务 cherry-pick 混合提交、修改其他任务生成物后不通知 owner。
- 分支落后集成分支时使用普通 merge/rebase 前先确认自己的 worktree 干净；不得用 hard reset 清理。

### Alembic 并行规则

迁移期仍使用统一 `backend/alembic/versions/` 时：

1. 每个领域只新增自己的 revision 文件，不修改其他领域已经发布的 migration。
2. 文件名包含日期、领域和目的；创建任务时登记 revision ID，避免同名。
3. 并行分支可以产生多个 Alembic head；功能 PR 合入集成分支时由基础设施负责人创建 merge
   revision，恢复单一 head。
4. 合并前必须通过空库 `upgrade heads/head`、约束测试和 seed 重跑测试；Portal/前端不得创建 migration。

## 5. 契约和 Mock 协作

- Markdown API 文档是冻结的业务输入；运行服务导出的 OpenAPI 是实现一致性产物。
- OpenAPI 快照统一放在 `docs/backend/openapi/<service>.json`，由对应 HTTP 服务 owner 更新。
- Staff/Tenant BFF 的 OpenAPI 是两个 React 应用唯一的网络契约；前端不直接从领域服务生成 client。
- 生成 client 分别写入各应用的 `src/api/generated/`，生成文件禁止手改。
- BFF 未完成时，前端可使用与 OpenAPI schema 同形的本地 fixture；Mock 只模拟响应，不复制租约、
  权限或状态迁移逻辑。
- 契约变更顺序固定为：文档评审 → producer OpenAPI/测试 → BFF consumer test → client 重新生成 →
  前端适配。破坏性变更必须升 API/event 版本。

## 6. 测试与 PR 门禁

每个功能 PR 合入 `integration/p0-skeleton` 前至少通过：

- 本任务 unit test；
- 数据服务的 migration/constraint/integration test；
- HTTP producer contract 和 BFF consumer contract；
- 前端 lint、unit/component test 和生产 build；
- `git diff --check`，且 PR 文件均属于任务所有权范围。

集成分支每天至少运行一次默认 P0 Compose。进入 `main` 前必须额外通过：

1. 空库 migration + Identity/domain seed；
2. 双端登录与 Gateway 路由；
3. 房源 → 联系 → 申请 → 审核 → 签署 → execute → active；
4. Tenant 报修及员工完成；
5. Tenant/Property Manager 报告生成与历史权限；
6. 私有资源不存在和越权 ID 返回相同 `404 resource_not_found`；
7. Redis/worker/API 重启下不丢关键业务状态。

## 7. 合并顺序

```text
main
  └─ integration/p0-skeleton
       ├─ refactor/p0-skeleton（先合）
       ├─ Identity / Property Leasing（契约与领域实现）
       ├─ Maintenance / Report（依赖领域授权）
       ├─ Staff/Tenant BFF（消费领域契约）
       └─ Staff/Tenant Web（消费 BFF 契约）
                ↓
           P0 Compose + E2E
                ↓
              main
```

并行表示开发可同时进行，不表示无序合并。前端可用 Mock 先行，但真实联调必须按依赖顺序进入集成
分支。最终只由一个集成 PR 合入 `main`，不允许多个功能 PR 同时绕过完整 P0 E2E。
