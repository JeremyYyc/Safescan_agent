# SafeScan 后端文档

## 阅读顺序

1. [目标仓库与服务目录](architecture/target-layout.md)
2. [微服务与数据所有权](architecture/service-boundaries.md)
3. [Controller / Service / Mapper / Model 分层](architecture/layering.md)
4. [服务目录](services/README.md)
5. [数据文档](data/README.md)
6. [API 契约规范](api/README.md)
7. [Identity Access Service API 清单](api/identity-access-api.md)
8. [本地开发与运行](operations/backend-manual.md)
9. [CI/CD](operations/ci-cd.md)
10. [后端交接索引](handover/README.md)

## 文档目录职责

| 目录 | 内容 | 变更触发条件 |
|---|---|---|
| `architecture/` | 系统边界、目标目录、分层与依赖规则 | 服务拆分、调用方向或部署单元变化 |
| `services/` | 每个服务的职责、表所有权、接口和依赖 | 服务行为、表或外部契约变化 |
| `data/` | 数据库入口、迁移和跨服务一致性 | schema、迁移或数据保留策略变化 |
| `api/` | HTTP、错误、分页、鉴权和幂等规范 | 公共 API 契约变化 |
| `operations/` | 启动、Docker、CI/CD、排障 | 运行方式或流水线变化 |
| `handover/` | 新成员接手顺序与发布检查 | 交付流程变化 |
| `decisions/` | 不可轻易逆转的架构决策（ADR） | 形成新的架构决策 |

## 当前与目标状态

当前报告与 Agent 基线仍位于 `backend/app`。Identity 第一轮已经迁入独立的
`backend/services/identity-access-service` FastAPI 进程；Gateway 将 `/api/v1/auth/*`、
`/api/v1/me*`、`/api/v1/iam/*` 路由到该服务，`/internal/v1/*` 仅容器网络可访问。
其余服务继续渐进迁移，在每个边界切换完成前原路径仍是对应功能的运行事实来源。

禁止为了“目录看起来像微服务”而复制业务逻辑或让两个路径同时写同一张表。
