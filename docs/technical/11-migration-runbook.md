# 迁移与发布 Runbook

## 1. 发布前

1. P00-A 阶段确认当前 MySQL CI required checks 全部通过；P00-C 以后确认 PostgreSQL required checks 全部通过。
2. 确认工作区、分支和数据库备份。
3. 在 test 环境运行 schema migration dry-run、现有 API 回归和 AI baseline。
4. 验证对象存储、模型 key、队列、health check 和回滚镜像。

## 2. P00 数据库迁移顺序

```text
冻结 MySQL 写入窗口
 → 备份/导出
 → PostgreSQL schema + 现有业务表数据导入（不创建 Property/Repair）
 → 行数、checksum、外键和业务抽样校验
 → 旧 API 回放
 → 切换 PostgreSQL 为唯一读写源
 → 观察与回退窗口
```

P00 数据库迁移完成并通过验收后，才进入下方 P0 应用迁移。

## 3. P0 迁移顺序

```text
新增 schema/表
 → Evidence 双写
 → LangGraph adapter 灰度
 → Product/Safety retrieval 灰度
 → 引用式报告灰度
 → 新 API 读取
 → 旧逻辑下线（稳定后）
```

不要同时进行数据库引擎切换、旧字段删除和工作流切换。

## 4. 回滚

- Workflow：关闭 `LANGGRAPH_ENABLED`，回到旧 Orchestrator。
- RAG：关闭 `RAG_SAFETY_ENABLED`，保留 Product BM25/旧回答路径。
- API：旧路径 adapter 继续提供服务。
- 数据：停止双写后从备份或反向脚本恢复；删除旧列前必须完成观察期。

## 4. 异常场景处理

| 场景 | 系统行为 | 用户行为 |
|---|---|---|
| 上传中断 | media 标记 incomplete，不启动 run | 继续上传或删除重传 |
| 模型超时 | 按策略重试，超限进入 failed | 查看原因并 retry |
| SSE 断开 | 事件保留，客户端从 event/status 补齐 | 页面刷新可恢复 |
| 重复启动 | 返回现有 active run | 继续等待，不重复提交 |
| 报告校验失败 | repair，超限不发布半成品 | 重新运行或联系支持 |
| 删除进行中 | 标记 deleting，异步清理 | 清理完成前不可重新使用同一资源 |

## 5. 验证清单

- 注册/登录和资源权限。
- 上传视频、处理进度、断线恢复。
- 报告风险、证据、引用和 PDF。
- 聊天上下文和知识库拒答。
- 删除聊天/媒体后的对象存储清理。
- 低置信度人工确认和 workflow resume。
- 监控错误率、P95、队列和模型成本。

## 6. 数据迁移原则

所有迁移脚本必须支持预演、输出统计、幂等和明确的 `--apply`；应用前备份，应用后做行数、外键、checksum 和业务抽样校验。
