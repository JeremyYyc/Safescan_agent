# SafeScan 项目文档中心

本目录是项目设计、开发、测试、运维和交接文档的统一入口。目录组织参考
[APLP](https://github.com/JeremyYyc/APLP.git) 的 `docs/handover`、按服务交接文档、
数据库目录和 CI/CD 文档做法，并结合 SafeScan 当前 PostgreSQL 多 schema 与 FastAPI
代码现状调整。

## 后端文档

- [后端文档总览](backend/README.md)
- [目标仓库与服务目录](backend/architecture/target-layout.md)
- [微服务与数据所有权](backend/architecture/service-boundaries.md)
- [Controller / Service / Mapper / Model 分层](backend/architecture/layering.md)
- [服务目录](backend/services/README.md)
- [数据文档](backend/data/README.md)
- [API 契约规范](backend/api/README.md)
- [本地开发与运行](backend/operations/backend-manual.md)
- [CI/CD](backend/operations/ci-cd.md)
- [后端交接索引](backend/handover/README.md)
- [架构决策记录](backend/decisions/README.md)

## 现有基线文档

这些文档仍是当前实现的事实来源；后端目录中的新文档负责给出目标边界和迁移规则。

- [全项目数据库框架设计](DATABASE-DESIGN.md)
- [当前技术架构](ARCHITECTURE.zh-CN.md)
- [代码路径索引](PATH_INDEX.zh-CN.md)
- [Nginx 网关](NGINX_GATEWAY.zh-CN.md)
- [日志与审计设计](LOGGING_DESIGN.zh-CN.md)
- [重构计划](REFACTOR_PLAN.zh-CN.md)
- [重构执行记录](REFACTOR_EXECUTION.zh-CN.md)
- [全项目技术分析](TECHNICAL_ANALYSIS.zh-CN.md)

## 文档维护规则

1. 数据表、API 或异步事件发生变化时，同一个 PR 必须更新对应服务文档。
2. 跨服务边界变化必须新增 ADR，并更新服务依赖图和数据所有权表。
3. 运维命令必须能从仓库根目录执行，敏感值只写变量名，不写真实值。
4. 每个服务的 `README.md` 只做快速入口，完整设计放在本目录，避免多份事实来源。
5. Mermaid 图保存为 Markdown 源文件；需要演示图片时再导出到 `docs/diagrams/`。
