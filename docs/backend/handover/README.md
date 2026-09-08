# 后端交接索引

该目录参考 APLP 的 `docs/handover` 作为接手项目的第一入口。

## 技术交接

- [后端文档总览](../README.md)
- [目标仓库与服务目录](../architecture/target-layout.md)
- [分层边界](../architecture/layering.md)
- [服务与数据所有权](../architecture/service-boundaries.md)
- [服务目录](../services/README.md)
- [数据库设计](../../DATABASE-DESIGN.md)
- [API 契约](../api/README.md)

## 运行与交付

- [本地开发与运行](../operations/backend-manual.md)
- [CI/CD](../operations/ci-cd.md)
- [当前代码路径索引](../../PATH_INDEX.zh-CN.md)
- [日志与审计](../../LOGGING_DESIGN.zh-CN.md)
- [重构执行记录](../../REFACTOR_EXECUTION.zh-CN.md)

## 接手检查清单

- [ ] 阅读目标边界并确认当前正在迁移的服务。
- [ ] 使用 `.env.example` 创建本地配置，确认没有真实秘密进入 Git。
- [ ] 运行后端测试、Compose config 和 smoke test。
- [ ] 检查 Alembic revision 与本地数据库一致。
- [ ] 确认对象存储 bucket、网关路由和报告 Worker 健康。
- [ ] 修改数据/API 时同步更新对应服务文档和 ADR。
- [ ] 发布前确认 CI 全绿、镜像可追溯且数据库有备份/回滚方案。
