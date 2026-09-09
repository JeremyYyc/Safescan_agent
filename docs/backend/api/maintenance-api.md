# Maintenance Service API

> 状态：目标契约；待实现
> 所有者：`maintenance-service` / `maintenance` schema
> 暴露范围：仅内部 `/internal/v1`；浏览器经 Portal API
> 容器监听端口：`8003`

## 1. 职责与边界

本服务是正式维修工单与时间线的唯一数据所有者。它通过 Property Leasing 的授权接口验证
房源、租约和 staff scope，通过 Identity 最小投影验证员工状态。Portal 不得自行创建工单记录，
Agent 草稿也不等于正式工单。

MVP 不启用 Agent draft/approval 页面，但保留现有表和未来接口边界。

Tenant 建单时必须由本服务向 Leasing 核验 subject 的唯一当前租约、本人承租关系、
`lease.status=active`，以及 lease.property 与请求 property 一致；不能只相信 token 中的 tenant。Prospect/Former Tenant
均不能创建新工单；已执行但尚未达到 starts_on 的待入住 Tenant 也不能创建。

## 2. 数据结构

```json
{
  "id": "order-uuid",
  "reference": "WO-20260908-001",
  "property": {"id": "property-uuid", "address": "Sydney NSW"},
  "lease_id": "lease-uuid",
  "summary": "Kitchen sink is leaking",
  "description": "Water appears under the cabinet",
  "priority": "normal",
  "status": "open",
  "reported_by": {"subject_id": "user-uuid", "display_name": "Tenant"},
  "assigned_staff": null,
  "version": 1,
  "created_at": "2026-09-08T10:00:00Z",
  "updated_at": "2026-09-08T10:00:00Z"
}
```

当前 `maintenance_orders` 需要在本服务 migration 中补充 `lease_id`、`description`。图片附件为
P1；届时由 Maintenance 新增自有 `maintenance_files/maintenance_attachments` 并管理私有对象，
不能借用 inspection-report 的业务文件表，也不能把 MinIO object key 直接交给客户端。

事件投影：

```json
{
  "sequence_no": 2,
  "event_type": "assigned",
  "actor": {"type": "staff", "display_name": "Manager"},
  "message": "Assigned to maintenance team",
  "occurred_at": "2026-09-08T11:00:00Z"
}
```

租客投影必须移除内部成本、供应商隐私、内部备注和不必要的员工身份信息。

## 3. API

### 3.1 健康检查

| 方法 | 路径 | 返回 |
|---|---|---|
| GET | `/health/live` | 进程存活 |
| GET | `/health/ready` | DB、migration 和必要内部依赖可用 |

### 3.2 工单

| 方法与路径 | 请求 | 返回／权限 |
|---|---|---|
| `POST /internal/v1/maintenance-orders` | `property_id,lease_id?,summary,description?,priority`；幂等键 | `201 OrderView`；tenant 本人 active Lease 或有权 staff |
| `GET /internal/v1/maintenance-orders` | `mine=true property_id? status? assignee_id? priority? cursor? limit?` | Tenant 本人、Property Manager scope、Maintainer assignment 或 Manager Admin 全局投影 |
| `GET /internal/v1/maintenance-orders/{order_id}` | 无 | 资源级授权后的 OrderView；Manager Admin 可见租客/员工双方详细信息和完整审计时间线 |
| `PATCH /internal/v1/maintenance-orders/{order_id}` | `summary?,description?,priority?,version` | open 阶段报告人或 manager；受控字段 |
| `POST /internal/v1/maintenance-orders/{order_id}/assignments` | `assigned_staff_id,version,note?`；幂等键 | manager scope；open/assigned |
| `POST /internal/v1/maintenance-orders/{order_id}/transitions` | `to_status,version,note?,blocked_reason?`；幂等键 | 按角色和状态机 |
| `POST /internal/v1/maintenance-orders/{order_id}/comments` | `content,visibility,client_message_id` | `201 EventView`；customer 只能 public |
| `GET /internal/v1/maintenance-orders/{order_id}/events` | `cursor? limit? projection=tenant|staff` | 脱敏时间线 |

创建命令先调用：

- tenant：`lease-action:check(subject, lease, property, maintenance:create)`；
- staff：`property-access:check(staff, property, maintenance:create_assigned)`。

Leasing 授权响应必须包含 `lease_version` 和 `relationship_version`。Maintenance 在写事务提交前
用这些版本进行第二次条件校验；Lease 状态或承租关系变化、依赖不可确认时不创建工单，并返回 `lease_access_required` 或
`dependency_unavailable`。后续事件用于关闭能力和失效缓存，不能替代提交前校验。正式创建事务
包括 order、`reported` event 和 outbox。

Manager Admin 投影遵循 Staff Portal `AdminMaintenanceOrderView`：本服务返回 order、property/lease
public ID、reporter/assignee public ID、描述、状态和带 visibility 的完整时间线；姓名与联系方式由
BFF 向 Identity 批量补齐。Property Manager/Maintainer 不得获得 Admin 投影，任何投影都不返回
内部数据库 ID、完整 IP/UA、对象 key 或认证数据。

### 3.3 内部工作投影

| 方法与路径 | 用途 |
|---|---|
| `POST /internal/v1/projections/orders:batch` | Portal 按 ID 批量聚合，最多 200 |
| `GET /internal/v1/maintenance-orders/{id}/work-context` | Maintainer 的最小房源、联系人和报告引用 |
| `POST /internal/v1/authorizations/order-access:check` | 其他受信服务验证 order 与 actor 关系 |
| `POST /internal/v1/privacy/subject-deletions:check` | `subject_id`；返回 open/assigned/in_progress/blocked 工单 blockers；Identity 删除前 fail-closed 检查 |
| `POST /internal/v1/privacy/subject-deletions/{request_id}` | Identity deletion worker 幂等删除 subject 工单、评论和可识别字段并返回处理状态 |

### 3.4 Agent 草稿（不在本 PRD UI 范围）

| 方法与路径 | 说明 |
|---|---|
| `POST /internal/v1/maintenance-drafts` | 只创建 mock/live 草稿，不创建正式工单 |
| `POST /internal/v1/maintenance-drafts/{id}/submit` | live 草稿提交审批 |
| `POST /internal/v1/approval-requests/{id}/decisions` | 批准/拒绝；仍需显式 convert |
| `POST /internal/v1/maintenance-drafts/{id}/convert` | 重新鉴权、幂等创建正式工单 |

## 4. 状态机

| 当前状态 | 允许目标 | 谁可以执行 |
|---|---|---|
| open | assigned, cancelled | scope manager；报告人仅可取消未处理工单 |
| assigned | in_progress, cancelled, assigned(改派) | assigned maintainer 或 scope manager |
| in_progress | blocked, completed, cancelled | assigned maintainer；manager 可接管 |
| blocked | in_progress, completed, cancelled | assigned maintainer 或 scope manager |
| completed | 无 | 终态；重开需未来专用命令 |
| cancelled | 无 | 终态 |

每次变更使用 `UPDATE ... WHERE id=? AND version=?`，成功后 version+1 并在同一事务追加事件。

## 5. 错误码

错误结构和 HTTP 映射遵循 [统一错误契约](README.md)。本服务子码：
`lease_access_required`、`property_access_denied`、`order_not_found`、`order_state_conflict`、
`assignee_inactive`、`assignee_not_allowed`、`version_conflict`、`idempotency_conflict`、
`attachment_unavailable`、`open_maintenance_orders_block_deletion`、`dependency_unavailable`、
`dependency_timeout`、`dependency_invalid_response`。

资源不存在或授权导致不可见时统一返回 HTTP 404；本服务内部可保留 `order_not_found`、
`property_access_denied` 等诊断子码，Portal 面向浏览器必须统一为 `resource_not_found`。参数合法但
状态不允许返回 409；下游授权依赖不可确认时返回 503，不得 fail-open。

## 6. 缓存与高并发

- 工单详情可 cache-aside 5–15s，key 包含 order version 和投影类型；写后删除。
- Tenant/assignee 列表可缓存 5–10s；不缓存 401/403。
- Property/Identity 最小投影 L1 30s + Redis L2 1–5min，但 active employment、本人承租关系和
  Lease 状态的最终敏感判断应回源或使用严格版本缓存。
- 限流使用 Redis：tenant 建单建议 10 次/小时/subject，评论 60 次/分钟/thread；具体值配置化。
- `Idempotency-Key + actor + operation` 在数据库持久化为权威；Redis 只减少热点重复请求。
- 列表使用 `(created_at,id)` cursor，manager/assignee 使用现有组合/部分索引。
- 批量获取 actor/property，禁止列表逐行调用 Identity/Leasing 形成 N+1。

## 7. 事件

| 事件 | payload |
|---|---|
| `maintenance.order_created.v1` | `order_id,property_id,lease_id?,reported_by_subject_id,priority,version` |
| `maintenance.order_assigned.v1` | `order_id,assigned_staff_id,assigned_by_staff_id,version` |
| `maintenance.order_changed.v1` | `order_id,from_status,to_status,version,occurred_at` |
| `maintenance.order_completed.v1` | `order_id,property_id,completed_at,version` |

不得在事件中发送完整描述、租客联系方式或内部备注。

## 8. 契约测试

1. Prospect、无关 tenant 和 former tenant 无法新建工单；工单读取必须命中本人历史承租关系或员工 scope。
2. Tenant A 无法通过 ID 获取 Tenant B 的工单。
3. Manager 缺少 property scope 时不能分派；Maintainer 只能更新自己的工单。
4. 并发 version 更新只有一个成功；重复幂等键不增加事件。
5. 非法状态跳转均返回稳定 409。
6. 租客时间线不泄漏 internal-only 事件字段。
7. 请求中的 lease/property 与 Leasing 返回的唯一当前租约不一致时拒绝且不产生任何工单数据。
8. 授权首次检查后 lease version 或 relationship version 变化时，提交前二次校验阻止创建。
9. Manager Admin 可查看全部工单双方详情；其他角色仍按 scope/assignment 投影脱敏。
10. subject deletion 重放幂等删除用户相关工单/评论，不因对象清理失败提前完成回执。
11. executed 待入住 Lease 不能创建工单；starts_on 后 lifecycle 激活才开放。
12. 任一非终态工单阻止 subject deletion；全部完成/取消后检查通过且删除处理可幂等重放。
