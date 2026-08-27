# 部署与运维文档

## 1. 环境

| 环境 | 用途 |
|---|---|
| local | 开发和单元测试 |
| test | 集成、评测和迁移预演 |
| staging | 灰度、模型和数据回放 |
| production | 正式用户 |

配置通过环境变量或 secret manager 注入；严禁提交真实 API Key。模型、数据库、对象存储和索引连接分别配置。

## 2. 部署单元

P00 将现有 Docker 数据库替换为 PostgreSQL；PostgreSQL 是唯一事实源，pgvector 在 RAG 阶段单独启用。现有 `db + backend + frontend + gateway` 继续兼容，worker 和对象存储应独立 health check。API 与 worker 分离扩缩容。

## 3. 健康检查

`/health/live` 只检查进程；`/health/ready` 检查数据库、对象存储和模型 Provider 配置。启动不因一次外部模型不可用而假装 ready。

## 4. 可观测性

日志字段：`request_id`、`user_id_hash`、`inspection_id`、`workflow_run_id`、`node`、`duration_ms`、`status`、`error_code`。指标包括任务成功率、节点耗时、模型成本、检索命中率、SSE 断线率和队列长度。视频内容只用对象 key/hash，不记录原始内容。

## 5. 发布

采用 feature flag：`LANGGRAPH_ENABLED`、`RAG_SAFETY_ENABLED`、`REPORT_CITATIONS_ENABLED`、`HITL_ENABLED`。发布顺序为 migration dry-run → deploy → smoke test → 小流量 → 指标观察 → 全量。每个 flag 必须定义默认值、负责人和回滚条件。
