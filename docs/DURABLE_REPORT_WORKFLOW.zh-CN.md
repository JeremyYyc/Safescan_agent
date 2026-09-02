# 可恢复报告工作流

## 目标与边界

视频报告生成会经过帧提取、视觉分析、多个模型调用、报告修复和落库，可能持续很久。HTTP/SSE 连接不是任务生命期的可靠载体。本方案把任务提交和执行分离：PostgreSQL 负责可靠投递与状态查询，LangGraph PostgreSQL checkpoint 负责节点级恢复。

## 架构

```text
POST /processVideoStream
  -> report_jobs (queued) + report_job_events
  -> dedicated backend-worker -- SKIP LOCKED claim + lease
  -> LangGraph (thread_id = report_jobs.job_id)
       -> PostgresSaver checkpoint after each completed node
  -> report_jobs (succeeded|failed) + durable events
  -> API replays events to SSE client / client reconnects safely
```

`report_jobs` 是交付状态的真源，`report_job_events` 是可重放的进度日志；LangGraph 的 checkpoint 表是执行状态真源。两者用同一个不可预测的 job ID 关联。报告产物依旧通过原有 `persist` 节点写入，保持业务数据的事务边界。

## 状态与恢复策略

- 入队使用“每个 chat 仅一个 active job”的部分唯一索引，防止多请求重复执行。
- 领取使用 `FOR UPDATE SKIP LOCKED`，并写入带超时的 lease；worker 崩溃后 lease 过期即可被其他 worker 领取。
- worker 以相同 `thread_id` 调用图；重领任务时调用 LangGraph 的 resume（不再提交初始 state）。已完成节点由 checkpoint 恢复，避免重跑长视频阶段或已经完成的模型步骤。
- 失败不自动无限重试：本次实现保留失败事件与 checkpoint，后续重试 API 应显式将失败 job 重新排队并设定最大尝试次数。
- SSE 断连没有副作用；重新调用同一 chat 会得到 active job 并从 `report_job_events` 重放。

## 部署顺序

1. 安装 `langgraph-checkpoint-postgres` 并执行 `alembic upgrade head`。
2. 同时运行 API `backend` 和 `backend-worker`。worker 在迁移尚未完成时会等待并重试。
3. 监控 queued/running lease、attempt、失败率和每个节点事件的耗时。

## 已知后续项

当前 `PostgresSaver.setup()` 由 worker 启动路径调用，以初始化 LangGraph 自己管理的 checkpoint 表。生产化时建议把该初始化移入受控的发布/迁移作业，并新增显式“重试失败 job”API、心跳续租，以及 checkpoint/事件保留期清理策略。
