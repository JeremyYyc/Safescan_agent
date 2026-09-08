# ADR-0001：以数据所有权拆分后端微服务

- 状态：Accepted
- 日期：2026-09-08

## 背景

当前 FastAPI 代码集中在 `backend/app`，但目标数据模型已经按六个 PostgreSQL schema 划分。
如果只按 API 文件或技术能力拆目录，服务仍可能跨 schema 直接查询并形成分布式单体。

## 决策

以 `identity_access`、`property_leasing`、`maintenance`、`inspection_report`、`knowledge`、
`staff_agent` 为六个数据所有权边界。Portal API 不拥有业务数据；报告 Worker 属于
inspection-report-service。服务内部固定采用 Controller → Service → Mapper → Model，跨服务
仅使用版本化 API 或事件。

## 后果

- 每张表只有一个写入者，归属和团队职责明确。
- 本地可以共享一个 PostgreSQL 实例，但不能共享 ORM 或越权查询。
- 跨服务工作流接受最终一致性，需要幂等、outbox/inbox 和补偿。
- 拆分必须逐用例迁移，短期保留当前单体入口作为基线。

## 未选择方案

- 按 Controller 文件拆服务：没有数据所有权，边界不稳定。
- 所有服务共享统一 Mapper/ORM：降低短期重复，但会导致紧耦合和越权访问。
- 一次性搬迁全部代码：难以验证行为等价，回滚范围过大。
