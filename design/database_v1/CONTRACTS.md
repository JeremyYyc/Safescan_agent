# 两侧共享契约 v1（设计稿，尚无真实 endpoint）

## 身份上下文

网关验证登录令牌，服务间使用面向目标服务的短期签名凭证／token exchange。下游独立验证签发者、audience、过期时间和 organization，不信任浏览器或 Agent 生成的 staff_id/role。organization 对外公开入口由已配置站点或经验证请求上下文绑定，不能任意切换组织读取私有记录。

```json
{
  "subject": "opaque-user-id",
  "organization_id": "opaque-org-id",
  "persona": "staff",
  "actor_service": "staff-agent-service",
  "request_id": "opaque-request-id",
  "audience": "maintenance-service"
}
```

以上是经验证的声明，不是 API body 的自由输入。内部 SQL 使用 bigint；对外 ID 使用不透明字符串映射，并始终带资源所有权检查。以 `(organization_id, resource_type, resource_id)` 关联不同服务，禁止认为不同表相同 bigint 表示同一对象。

同一账号可以拥有多个 persona，切换必须经身份服务验证。未登录潜客仅能访问公开房源／公共政策；私有申请、预约、租约、账单与维修须登录。租客关联由 property-leasing 内 `parties.user_id` + `lease_tenants` 验证，不能根据用户自报手机号或姓名自动授权。

## 最小共享 API

| API | 员工侧 | 租户／潜客侧 | 实际数据所有者 |
|---|---|---|---|
| GET /v1/properties | 授权管理范围详情 | 已发布房源公开投影 | property-leasing |
| GET /v1/leases | lease:read + 管理范围 | 本人关联租约 | property-leasing |
| GET /v1/rent-invoices | rent:read + 管理范围 | 本人租约账单 | property-leasing |
| GET /v1/portfolio-metrics | portfolio_metrics:read 或批准的范围汇总 | 禁止 | property-leasing |
| POST /v1/applications | 权限允许时为业务建档 | 为自己申请 | property-leasing |
| GET /v1/applications | 授权范围 | 仅本人 | property-leasing |
| POST /v1/viewing-appointments | 授权排期 | 为自己预约公开房源 | property-leasing |
| GET /v1/maintenance-orders | maintenance:read + 管理范围 | 仅本人报修且仍获授权；不暴露内部供应商备注 | maintenance |
| POST /v1/maintenance-drafts | maintenance:draft + 范围；当前仅 Mock | 不开放员工草稿权限 | maintenance |
| POST /v1/maintenance-requests | 按实现能力和权限 | 本人有效租约下报修；后续实现 | maintenance |
| POST /v1/report-jobs | 文件与房源授权 | 本人文件与授权检查 | inspection-report |
| GET /v1/reports/{id} | 报告关联房源权限 | 本人或明确共享报告 | inspection-report |
| POST /v1/knowledge/search | 员工知识库 ACL | public 或 tenant 库，禁止 staff 库 | knowledge |

角色只决定“能做哪种操作”，资源关系决定“对哪条记录能做”。员工的 property:read_summary 不隐含 property:read。平台运营汇总不得通过全量个人明细返回后由 Agent 自行汇总。跨服务验证失败、下游超时、身份服务不可用时，对私有查询／写入失败关闭。

禁止租户 Agent 通过调用员工 Agent 间接获得员工权限。若未来允许跨 Agent 委派，仍保留原始 subject/persona 和权限上限。

## 响应与错误

```json
{
  "request_id": "req-demo",
  "status": "ok",
  "source": "mock",
  "data": {"items": [], "next_cursor": null},
  "effects": {"business_persisted": false, "approval_submitted": false}
}
```

统一错误代码：`UNAUTHENTICATED`、`FORBIDDEN`、`NOT_FOUND`、`INVALID_ARGUMENT`、`UNSUPPORTED`、`CONFLICT`、`UPSTREAM_UNAVAILABLE`。需要隐藏存在性的私有资源可统一 NOT_FOUND。服务日志保留真实拒绝原因但不把无权房源／租客信息返回模型。

列表统一 cursor 分页，最多 100 条；金额字符串 + ISO 币种；时间 ISO 8601 带时区，数据库 timestamptz；账单业务日期用 date。

写入要求 Idempotency-Key：服务按 `(organization, subject, operation, key)` 保存结果和请求摘要，同 key 不同参数返回 CONFLICT。本次草稿／预约表有去重字段，但完整幂等存储、摘要比较与 HTTP 重放逻辑仍待实现，不可只凭唯一键宣称 exactly-once。

## Agent 运行协议

员工侧 POST /v1/staff/requests：输入 query、session_id、idempotency_key；身份来自验证会话。原型输出 `execute/human/clarify/deny`；execute 是进入执行流程的决定，不是执行完成。

同学可以独立设计 POST /v1/tenant/requests。双方无需共享 prompt、内部链路或聊天表，统一资源 API 和错误格式即可。

建议同学的私有表（本轮不建 DDL）：

| 表 | 最小内容 |
|---|---|
| tenant_sessions | organization_id、user_id（匿名时可空）、session_key、persona、expires_at |
| tenant_messages | session_id、role、content、created_at |
| tenant_requests | session_id、original_text、route、status、idempotency_key |
| tenant_tasks | request_id、ordinal、intent、status、result |
| recommendation_contexts | session_id、预算／卧室／通勤偏好、版本、过期时间 |

推荐结果只保存 property_id 列表与来源版本，不复制正式房源表。匿名转登录的会话归属需服务端一次性认领校验；不能让用户填写 session_id 接管别人的历史。

## 事件契约

事件用于缓存失效、通知和读模型，不用于传递任意员工权限：

```json
{
  "event_id": "opaque-id",
  "event_type": "maintenance.order.updated",
  "schema_version": 1,
  "organization_id": "opaque-org-id",
  "aggregate_id": "opaque-order-id",
  "aggregate_version": 2,
  "occurred_at": "2026-09-07T08:00:00Z",
  "correlation_id": "opaque-request-id",
  "data": {"status": "in_progress"}
}
```

首批事件：property.listing.published、lease.updated、maintenance.order.updated、report.completed、knowledge.document.published、staff.scope.revoked。领域服务各自拥有 outbox/inbox；当前只提供员工侧 outbox 表作为示范，其他服务接事件时在本库新增相同机制。消费者按 event_id 去重，按 aggregate_version 防止乱序回退，重查资源时重新授权。敏感文档正文、联系方式、token 不进入事件。

## 协作验收场景

- 员工 Amy 能查询 HV-102，Ben 不能；David 只能获允许的汇总。
- 潜客可看公开 HV-101，不可看 HV-102 内部租约、账单或维修备注。
- 租户只能看自身租约；猜测其他 lease_id 不扩大权限。
- 两侧查询同一维修单应得到同一状态，各自字段投影不同。
- 员工多任务含草稿 → 整单 human，任何领域 API 都不被调用。
- 已创建模拟草稿只显示“模拟”，外部人工队列未接通时不得显示“已提交”。
- 跨组织逻辑引用不能靠数据库跨服务 FK 拦截，必须由服务授权测试覆盖。
