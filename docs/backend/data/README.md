# 后端数据文档

## 事实来源

- [全项目数据库框架设计](../../DATABASE-DESIGN.md)：完整表、关系、索引、安全和一致性设计。
- `backend/app/persistence/target_schema.py`：当前 SQLAlchemy 目标 metadata。
- `backend/alembic/versions/20260907_0001_microservice_baseline.py`：当前可执行迁移基线。
- `backend/tests/target_schema_invariants.sql`：数据库不变量验证。

文档描述“为什么”，metadata 描述“目标对象”，Alembic 描述“如何演进”。三者不一致时，不得
直接修改生产数据，应先在 PR 中明确预期并补齐迁移和测试。

## schema 所有权

| schema | 唯一写入者 | 允许的外部访问 |
|---|---|---|
| `identity_access` | identity-access-service | 身份 API、身份事件 |
| `property_leasing` | property-leasing-service | 房源/租赁 API、领域事件 |
| `maintenance` | maintenance-service | 维修 API、领域事件 |
| `inspection_report` | inspection-report-service/worker | 报告 API、任务领取、领域事件 |
| `knowledge` | knowledge-service | 检索/文档 API、索引任务 |
| `staff_agent` | staff-agent-service | Agent API、工作流 worker |

## 迁移规则

1. 迁移文件只追加，不修改已经共享或发布的 revision。
2. 采用 expand → backfill → switch → contract；破坏性收缩单独 PR。
3. 表和索引名称包含所属 schema/聚合语义，所有外键列建立索引。
4. 跨服务 public ID 不建物理外键，由 Service/Client 校验并通过事件修正投影。
5. DDL、数据回填和应用切换分别可观测、可重试；大表变更评估锁影响。
6. CI 至少执行空库 `alembic upgrade head` 和目标 schema 不变量测试。

## 数据变更 PR 清单

- [ ] 指明数据所有者和调用者。
- [ ] 更新服务文档与 ER/关系说明。
- [ ] 添加 Alembic revision，并在空库验证。
- [ ] 添加约束、索引、幂等和并发测试。
- [ ] 说明回填、回滚与旧字段删除时机。
- [ ] 检查日志、审计和敏感字段脱敏。
