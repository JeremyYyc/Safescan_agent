# maintenance-service

## 职责

负责正式维修工单、时间线事件、Agent 操作草稿和高风险操作审批。Agent 可以提出草稿，
只有维修 Service 能验证权限与状态并生成正式工单。

## 数据所有权

`maintenance_orders`、`maintenance_events`、`maintenance_drafts`、`approval_requests`，以及
本 schema 的 outbox/inbox 表。

## 模块建议

- Controllers：orders、events、drafts、approvals。
- Services：建单、分派、状态迁移、证据提交、审批执行。
- Mappers：MaintenanceOrder、MaintenanceEvent、Draft、ApprovalRequest。
- Clients：身份主体/权限、房源最小投影、报告发现项最小投影。

## 关键约束与测试

- 工单状态只通过显式状态机变化，每次变化追加事件。
- Maintainer 只能访问分配给自己的工单和最小工作上下文。
- 草稿不能作为正式业务事实；审批执行需要版本、幂等键和操作者审计。
- 跨服务引用只保存 public ID，不建立跨 schema 外键。
