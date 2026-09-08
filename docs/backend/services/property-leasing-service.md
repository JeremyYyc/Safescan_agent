# property-leasing-service

## 职责

负责大楼、房源、资源范围、客户主体、潜客流程、联系线程、看房、申请、租约、账单、支付
和收藏。租客身份阶段由本服务发布事实事件，身份服务消费后形成身份投影。

## 数据所有权

`buildings`、`properties`、`staff_building_scopes`、`staff_property_scopes`、`parties`、
`property_owners`、`prospect_cases`、`prospect_case_events`、`prospect_contact_threads`、
`prospect_contact_messages`、`leases`、`lease_tenants`、`lease_access_grants`、
`rent_invoices`、`payments`、`payment_allocations`、`tenancy_applications`、
`viewing_appointments`、`property_favorites`，以及本 schema 的 outbox/inbox 表。

## 模块建议

- Controllers：properties、prospects、viewings、applications、leases、billing。
- Services：房源发布、潜客状态机、申请审批、租约签署、账单核销。
- Mappers：按聚合拆为 Property、Prospect、Lease、Billing、Viewing。
- Events：`lease.executed`、`lease.ended`、`property.status_changed`。

## 关键约束与测试

- 市场查询只能返回已发布投影；内部读取还要叠加员工资源范围。
- 双方签署完成后才能进入 executed；同一房源有效租期不能冲突。
- 金额分配必须在事务内核销，不能超过支付额或账单余额。
- 转租客事件使用稳定 event ID，身份服务消费必须幂等。
