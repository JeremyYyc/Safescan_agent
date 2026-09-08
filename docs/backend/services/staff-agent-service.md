# staff-agent-service

## 职责

负责员工与 Agent 的会话、完整消息时间线、请求拆分、意图、任务 DAG、工作流检查点、工具
调用、人工分流、A2A 和审计。它是编排者，不拥有正式房源、租约、工单或报告事实。

## 数据所有权

`agent_definitions`、`prompt_versions`、`staff_sessions`、`staff_messages`、
`staff_message_attachments`、`staff_message_streams`、`staff_requests`、
`staff_request_events`、`staff_clarifications`、`staff_session_resources`、
`staff_context_summaries`、`intent_runs`、`staff_tasks`、`task_dependencies`、
`workflow_checkpoints`、`task_runs`、`tool_calls`、`task_results`、`human_cases`、
`a2a_delegations`、`audit_events`，以及本 schema 的 outbox/inbox 表。

## 模块建议

- Controllers：sessions、messages、requests、streams、human-cases。
- Services：会话、请求规划、任务调度、恢复、人工分流、审计。
- Mappers：SessionTimeline、Request、TaskGraph、Run、ToolCall、HumanCase。
- Clients/Tools：每个领域服务一个显式客户端和最小权限工具适配器。
- Workflows：LangGraph 状态和节点只依赖 Service/Tool 接口。

## 关键约束与测试

- 用户消息、请求、任务、运行和工具调用均可通过 correlation ID 追踪。
- Prompt 和 Agent 定义版本化，运行记录引用确定版本。
- 高风险写操作先形成草稿/审批；工具参数在调用前按 schema 校验。
- 工作流可从 checkpoint 恢复；重复回调和事件不得重复执行业务写入。
