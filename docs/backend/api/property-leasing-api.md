# Property Leasing Service API

> 状态：目标契约；待实现
> 所有者：`property-leasing-service` / `property_leasing` schema
> 暴露范围：仅内部 `/internal/v1`；浏览器必须经 Portal API
> 容器监听端口：`8002`

## 1. 职责与授权

本服务拥有大楼、房源、员工资源 scope、party、潜客案件、真人联系线程、看房、租房申请、
租约、签署、账单与支付。Portal 只能调用本接口，不能直连本 schema。

授权规则：

- Guest/customer 的市场查询只返回 `public + marketing` 投影。
- Customer 私有查询必须以 token subject 解析唯一 party，再校验 case、application，或
  `lease_tenants → lease` 承租关系、Lease 状态及资源归属。
- 一个 customer 同时最多拥有一个 pending_signature/executed/active 当前租约；只有 prospect/former_tenant
  可以创建申请和进入签署，tenant 只能读取历史申请及当前租约。
- Staff 必须满足 active staff、permission 与 building/property/case scope 三者交集。
- 内部调用使用 audience=`property-leasing-service` 的委派 token；不信任公网
  `X-Actor-Subject`。

## 2. 公共结构

### 2.1 PropertyMarketView

```json
{
  "id": "property-uuid",
  "reference": "P-1001",
  "address": "Sydney NSW",
  "bedrooms": 2,
  "bathrooms": 1,
  "weekly_rent": "650.00",
  "currency": "AUD",
  "availability": "available",
  "attributes": {"cover_image_url": "/api/v1/tenant/assets/..."},
  "updated_at": "2026-09-08T10:00:00Z"
}
```

市场投影不得包含 owner、当前租客、内部备注、scope、未公开申请或租约 ID。

### 2.2 ProspectCaseView

```json
{
  "id": "case-uuid",
  "property": {"id": "property-uuid", "reference": "P-1001", "address": "Sydney NSW"},
  "stage": "contacted",
  "status": "open",
  "assigned_consultant": {"id": "staff-uuid", "display_name": "Alex"},
  "version": 2,
  "updated_at": "2026-09-08T10:00:00Z"
}
```

### 2.3 ApplicationView

```json
{
  "id": "application-uuid",
  "reference": "APP-20260908-001",
  "case_id": "case-uuid",
  "property_id": "property-uuid",
  "status": "submitted",
  "desired_start_on": "2026-10-01",
  "term_months": 12,
  "occupants": 2,
  "note": "",
  "version": 2,
  "submitted_at": "2026-09-08T10:00:00Z"
}
```

`desired_start_on/term_months/occupants/note` 是 MVP 相对当前表结构需要补充的申请字段；实现前
应通过 property-leasing 自有 migration 增加，不得塞入 Portal 数据库。

### 2.4 LeaseView

```json
{
  "id": "lease-uuid",
  "reference": "L-2026-001",
  "property": {"id": "property-uuid", "address": "Sydney NSW"},
  "starts_on": "2026-10-01",
  "ends_on": "2027-09-30",
  "weekly_rent": "650.00",
  "currency": "AUD",
  "status": "pending_signature",
  "document": {"id": "lease-document-uuid", "version": 1, "terms_digest": "sha256:..."},
  "tenant_signers": [{"subject_id": "user-uuid", "status": "pending", "signed_at": null}],
  "company_signed_at": null,
  "offer_expires_at": "2026-09-15T10:00:00Z",
  "executed_at": null,
  "version": 2
}
```

现有 schema 需新增：

- `lease_documents(public_id,lease_id,version,terms_payload,terms_digest,status,created_by_subject_id,
  created_at)`；唯一 lease+version，issued 后不可变；
- `lease_signature_events(lease_id,lease_document_id,signer_subject_id?,signer_staff_id?,side,
  terms_digest,ip_hash,user_agent_hash,occurred_at,correlation_id)`；只追加。
- `customer_lease_slots(customer_subject_id PK,lease_id,status,reserved_at,version)`；在
  `pending_signature/executed/active` 期间占用。进入待签时 INSERT；取消、过期、结束或终止时，
  在同一事务按 `customer_subject_id + lease_id` 条件 DELETE。该表只保存当前占位，历史事实保留在
  `leases/lease_tenants` 和事件中；主键是“一人同时只有一个当前租约”的数据库最终保护。
- lease 增加 `offer_expires_at`，状态补齐 `expired`；生命周期 worker 负责按时间幂等激活、过期和
  自然结束。
- lease 增加必填 `application_id` FK 并建立唯一约束；一份 approved application 最多生成一份
  lease，合同内容变化通过 lease document version 表达，不重复创建 lease。
- application 增加 `closed_reason,closed_at,winning_lease_id`；系统自动收口时
  `closed_reason=another_lease_executed`，`winning_lease_id` 指向获胜 lease。
- PostgreSQL 启用 `btree_gist`，对 `(property_id, daterange(starts_on,ends_on,'[]'))` 建立条件
  EXCLUDE 约束，仅覆盖 `pending_signature/executed/active`，作为房源租期不重叠的最终保护。

Lease 状态机为：`draft → pending_signature → executed → active → ended`；执行前可进入
`cancelled/expired`，执行后可进入 `terminated`。`cancelled/expired/ended/terminated` 为终态。
MVP 不将产品确认描述为合规第三方电子签章。

## 3. 健康检查

| 方法 | 路径 | 返回 |
|---|---|---|
| GET | `/health/live` | 进程存活 |
| GET | `/health/ready` | DB、migration 与必要 Identity/JWKS 依赖可用 |

## 4. 房源和 scope API

| 方法与路径 | 请求 | 返回／权限 |
|---|---|---|
| `GET /internal/v1/market-properties` | `q? bedrooms? min_rent? max_rent? cursor? limit?` | `PropertyMarketView[]`；guest/customer/staff market scope |
| `GET /internal/v1/market-properties/{property_id}` | 无 | `PropertyMarketView`；仅公开投影 |
| `GET /internal/v1/properties` | `status? building_id? scope=assigned cursor?` | StaffPropertyView[]；按 staff scope |
| `GET /internal/v1/properties/{property_id}` | `projection=management|lease_prepare|work_context` | 按 permission/scope 裁剪 |
| `POST /internal/v1/properties` | 房源基本字段；幂等键 | P1；`201 StaffPropertyView`；`property:create` |
| `PATCH /internal/v1/properties/{id}` | 可变字段、`version` | P1；更新投影；`property:manage_*` |
| `POST /internal/v1/properties/{id}/publish` | `version` | P1；public marketing；管理权限 |
| `POST /internal/v1/properties/{id}/unpublish` | `version,reason` | P1；private/staff；管理权限 |
| `GET /internal/v1/buildings` | `scope=assigned` | StaffBuildingView[] |
| `PUT /internal/v1/buildings/{id}/staff-scopes/{staff_id}` | `scope_role,valid_from,valid_until?` | P1；管理 scope；`scope:manage` |
| `DELETE /internal/v1/buildings/{id}/staff-scopes/{staff_id}` | `reason,version` | P1；`204`；`scope:manage` |
| `POST /internal/v1/authorizations/property-access:check` | `subject_id,property_id,action,lease_id?` | 领域级 allow/deny + property version；报告生成时同时返回该 property 的 `active_lease_id?`；受信服务调用 |

P0 的 `PropertyMarketView` 与 `StaffPropertyView` 均返回房源本身的结构化元数据：
`location{address,latitude?,longitude?}`、`bedrooms`、`bathrooms`、`parking_spaces`、
`has_parking`、`display_image_urls[]`、`building_id/building`、`floor_area_sqm?` 和
`floorplan_url?`。同时保留顶层 `address` 兼容既有消费者。展示图片保持有序；历史
`attributes.cover_image_url` 与 `attributes.floorplan_url` 在迁移时提升到正式字段，未知历史车位
保持 `null`，不推断为无车位。房源增删改与媒体上传仍属于 P1。

市场查询的 `availability` 必须由房源状态、有效申请和重叠租约共同计算，不能只相信可手工修改
的 status。

## 5. 联系业务员与潜客案件 API

| 方法与路径 | 请求 | 返回／权限 |
|---|---|---|
| `POST /internal/v1/contact-requests` | `property_id,content,client_message_id`；幂等键 | `201 CaseWithThreadView`；登录 customer |
| `GET /internal/v1/prospect-cases` | `mine=true stage? status? cursor?` | Customer 本人或 Staff 分配案件列表 |
| `GET /internal/v1/prospect-cases/{case_id}` | 无 | 本人 customer／有权 staff |
| `PATCH /internal/v1/prospect-cases/{case_id}` | `stage?,status?,version,reason?` | Staff 推进状态 |
| `POST /internal/v1/prospect-cases/{case_id}/assignments` | `consultant_staff_id,version,reason`；幂等键 | Admin/team manager 改派 |
| `GET /internal/v1/prospect-cases/{case_id}/events` | `cursor? limit?` | 脱敏时间线 |
| `GET /internal/v1/contact-threads/{thread_id}/messages` | `after_sequence? limit?` | 案件客户／当前有权业务员 |
| `POST /internal/v1/contact-threads/{thread_id}/messages` | `content,client_message_id` | `201 MessageView`；唯一键防重 |

`POST contact-requests` 必须以一个事务创建／复用 party、case、thread 和首条消息。若没有可分配
业务员，case 可保持未分配并返回 `assigned_consultant=null`，但消息不可丢失。
P0 选择规则固定为按 staff public ID 排序 active Leasing Consultant，以
`hash(customer_subject_id,property_id)` 取模选择；列表为空或提交前失效则保持 unassigned。无需
负载统计、跨服务锁或独立调度服务。候选列表与单个目标校验均来自 Identity 的实时 active staff
投影，不读取静态环境变量；Manager Admin 改派必须携带 `prospect:manage_all`、幂等键和当前
case version，并同步更新 active thread、case event 与 outbox。

## 6. 看房 API（P1）

| 方法与路径 | 请求 | 返回／权限 |
|---|---|---|
| `GET /internal/v1/properties/{id}/viewing-slots` | `from,to` | 可预约时段；公开/客户投影 |
| `POST /internal/v1/viewings` | `property_id,starts_at,ends_at`；幂等键 | `201 ViewingView`；customer |
| `GET /internal/v1/viewings` | `mine=true status? cursor?` | Customer 本人或 staff 工作队列 |
| `POST /internal/v1/viewings/{id}/cancel` | `reason,version` | Customer 本人／业务员 |
| `POST /internal/v1/viewings/{id}/complete` | `version,note?` | Staff host |

## 7. 租房申请 API

| 方法与路径 | 请求 | 返回／权限 |
|---|---|---|
| `POST /internal/v1/applications` | `case_id,property_id,desired_start_on,term_months,occupants,note?`；幂等键 | `201 ApplicationView`；case 本人且 customer_status=prospect/former_tenant |
| `GET /internal/v1/applications` | `mine=true status? cursor?` | Customer 本人、分配 staff 或 Manager Admin 全局 |
| `GET /internal/v1/applications/{id}` | 无 | 有资源关系的 customer/staff |
| `PATCH /internal/v1/applications/{id}` | draft 可编辑字段、`version` | 仅 prospect/former_tenant 申请人且 draft |
| `POST /internal/v1/applications/{id}/submit` | `version,attestation=true`；幂等键 | prospect/former_tenant；draft→submitted |
| `POST /internal/v1/applications/{id}/start-review` | `version` | submitted→reviewing；业务员 |
| `POST /internal/v1/applications/{id}/approve` | `version,decision_note?`；幂等键 | reviewing→approved；业务员 |
| `POST /internal/v1/applications/{id}/reject` | `version,reason_code,decision_note?`；幂等键 | reviewing→rejected |
| `POST /internal/v1/applications/{id}/withdraw` | `version,reason?` | applicant；draft/submitted/reviewing，或仅关联 draft lease 的 approved application |

人工状态：`draft → submitted → reviewing → approved|rejected`，以及非终态→`withdrawn`。
系统收口状态：`draft/submitted/reviewing → ineligible`，`approved → expired`。
Tenant 可调用 GET 查看历史，但创建、编辑和提交返回 `403 customer_not_eligible_for_lease`。

撤回 approved application 时，仅允许关联 Lease 仍为 draft，并在同一事务把 application、Lease、case
分别改为 `withdrawn/cancelled/lost+closed`。Lease 已进入 pending_signature 后，application withdraw
返回状态冲突；Customer 必须调用 Lease decline，由该命令原子取消 Lease、释放 slot、将 application
改为 withdrawn 并关闭 case。员工取消或 lifecycle 过期待签 Lease 时，关联 application 改为 expired、
case 改为 lost/closed。上述事务均重新计算 property availability 并写 outbox，避免 approved
application、draft Lease 或 under_offer 房源形成悬空状态。

同一客户可并行申请不同 property。任一租约执行时，本服务在同一事务把该客户其他
draft/submitted/reviewing 申请改为 ineligible，并把除获胜 application 外的所有 approved 申请改为
expired，无论其是否已生成 lease。若其他 approved application 已生成非终态 draft lease，则对应
draft lease 同时改为 cancelled。所有自动失效申请写入
`closed_reason=another_lease_executed,closed_at,winning_lease_id`，对应 case 统一改为 lost/closed；
每条变化追加事件和 outbox。重复执行或事件重放不得重复收口。

## 8. 租约与签署 API

| 方法与路径 | 请求 | 返回／权限 |
|---|---|---|
| `POST /internal/v1/leases` | `application_id,starts_on,ends_on,weekly_rent,currency,terms_payload,offer_expires_at`；幂等键 | `201 LeaseView`；从 application applicant 推导单一 tenant subject；`lease:prepare` 且 approved |
| `GET /internal/v1/leases` | `mine=true status? property_id? cursor?` | Customer 按 applicant/signer/承租关系；staff 按 scope；Manager Admin 全局 |
| `GET /internal/v1/leases/{lease_id}` | `projection=customer|staff|admin` | Customer 按 applicant/signer/承租关系，staff 按 scope；admin 返回租客与员工双方详细信息和审计摘要 |
| `GET /internal/v1/leases/{lease_id}/documents/current` | 无 | 当前不可变合同 HTML/terms/digest；applicant/signer/承租关系或 staff scope |
| `PATCH /internal/v1/leases/{lease_id}` | draft 条款、`version` | `lease:prepare`；仅 draft |
| `POST /internal/v1/leases/{lease_id}/send-for-signature` | `lease_document_id,version`；幂等键 | 锁定 customer party 并原子占用唯一 lease slot，draft→pending_signature |
| `POST /internal/v1/leases/{lease_id}/tenant-signatures` | `lease_document_id,terms_digest,accepted=true,version`；幂等键 | 仅 prospect/former_tenant；当前 customer 只能签自己且 slot 匹配 |
| `POST /internal/v1/leases/{lease_id}/company-signature` | `lease_document_id,terms_digest,accepted=true,version`；幂等键 | `lease:execute` staff |
| `POST /internal/v1/leases/{lease_id}/execute` | `version`；幂等键 | 双方签完后原子执行 |
| `POST /internal/v1/leases/{lease_id}/cancel` | `reason_code,version`；幂等键 | draft/pending_signature；有权 staff，或本人 pending signer 走 Portal decline；同步关闭关联 application/case |
| `POST /internal/v1/leases/{lease_id}/expire` | `as_of,version`；幂等键 | 仅 lifecycle service；pending 且超过 offer_expires_at |
| `POST /internal/v1/leases/{lease_id}/activate` | `as_of,version`；幂等键 | 仅 lifecycle service；executed 且 starts_on 已到 |
| `POST /internal/v1/leases/{lease_id}/end` | `effective_at,version`；幂等键 | lifecycle service 自然到期，或 Manager Admin 补偿命令 |
| `POST /internal/v1/leases/{lease_id}/terminate` | `effective_at,reason,version`；幂等键 | 高风险权限 + 审计 |
| `POST /internal/v1/authorizations/lease-action:check` | `subject_id,lease_id,property_id?,action` | `allowed,lease_id,property_id,status,lease_version,relationship_version`；按承租关系、Lease 状态和资源归属实时判断；受信服务 |

创建租约时不得接受 tenant_subject_id。服务必须锁定 approved application，并通过
`application.applicant_id → parties.subject_id` 推导承租人；subject 缺失、申请人与 case 不一致或
application 已被使用时拒绝且不创建 lease。`leases.application_id` 必须为 `NOT NULL UNIQUE FK`，
数据库唯一约束是“一份 application 最多生成一份 lease”的最终保护。
创建 lease 和 send-for-signature 前必须通过 Identity 最小投影确认 applicant subject 仍 active 且非
`deletion_pending`；依赖不可确认时 fail-closed。员工权限不能绕过客户删除状态。

进入待签时通过 `INSERT customer_lease_slots` 获取 subject 唯一槽位；唯一冲突返回
`409 customer_already_has_lease`。执行租约的单事务必须包括：锁定 property/customer slot、确认
所有签名、再次验证 PostgreSQL property/date exclusion、设置 executed、更新 slot、
转化获胜 case、收口该客户其他申请/case/draft lease、更新 property 与写 outbox。任何一步失败
全部回滚。待签合同取消/过期或租约结束/终止时必须在同一事务释放 slot；取消/过期还必须同步关闭
关联 application/case 并重新计算 property availability。
`draft` 是内部合同准备记录，不算当前租约且不占 slot；多个 approved application 可以各有 draft，
但并发 send-for-signature 最多一个成功。

Customer 读取租约分两阶段：执行前通过不可伪造的 application applicant/lease signer 关系读取
待签合同；执行后通过 `lease_tenants.party_id → parties.subject_id` 读取本人当前或历史合同。
Identity 的 customer status 只是页面能力上限，不能替代领域承租关系校验，避免越权和
“必须先执行才能看到合同、但必须先看合同才能签署”的循环。

合同执行后 Customer 立即成为 Tenant，但 `executed` 只开放合同与待入住房产读取。Maintenance 和
Report 的创建授权必须额外要求 `lease.status=active`；达到 building timezone 下的 `starts_on` 后由
lifecycle worker 激活。P0 不支持提前交接；未来 `early_access_from` 必须作为显式字段和独立规则。

生命周期 worker 按 `(status,offer_expires_at|starts_on|ends_on,id)` cursor 分批处理并使用
`FOR UPDATE SKIP LOCKED`；cancel/expire 发生在执行前，不发布 customer status 变化；end/terminate
释放当前 slot 并发布 former_tenant。历史读取能力直接由本人承租关系与 `ended/terminated`
状态判定。失败任务可幂等重跑，Manager Admin 可对单个 lease
执行受审计的补偿 end，但不能绕过日期、签名和状态机。

`offer_expires_at` 是 UTC timestamp。`starts_on/ends_on` 是 property 所在地日历日期，生命周期在
building timezone 解释；`ended` 在 ends_on 当地日结束后生效。building 必须配置 IANA timezone，
不得使用 Portal 浏览器时区决定合同状态。

条款变化必须生成新的 lease document version 并清除/作废旧版本签署状态；签名时间仍同步回写
现有汇总字段以便查询。

`projection=admin` 必须遵循 Staff Portal `AdminLeaseView` 字段契约；Property Leasing 返回其拥有的
lease/property/application/billing 字段和 subject/staff public ID，人员展示信息由 BFF 向 Identity
批量补齐。领域服务不得跨 schema JOIN Identity，也不得返回 bigint 内部 ID。

## 9. 账单 API

| 方法与路径 | 请求 | 返回／权限 |
|---|---|---|
| `GET /internal/v1/leases/{lease_id}/invoices` | `status? cursor?` | 本人承租关系且 Lease 为 executed/active/ended/terminated，或 staff scope |
| `GET /internal/v1/invoices/{invoice_id}` | 无 | 同上 |
| `POST /internal/v1/invoices` | 账期、金额；幂等键 | 授权 staff；P1 |
| `POST /internal/v1/payments` | 支付与 allocations；幂等键 | P1；内部支付适配器；不在 P0 UI |

P0 只读接口必须返回合同租金条款、invoice/payment 历史列表和明确 totals；新租约尚无账单或缴费时
返回空列表与零 totals，不伪造付款记录。创建账单、收款和支付集成不阻塞租赁主链路。

## 10. 内部批量投影

| 方法与路径 | 用途 |
|---|---|
| `POST /internal/v1/projections/properties:batch` | Maintenance/Report 批量获取房源最小投影和 actor access |
| `POST /internal/v1/projections/leases:batch` | Portal 聚合本人租约摘要 |
| `POST /internal/v1/projections/parties:batch` | 授权后返回最小显示名，最多 200 |
| `POST /internal/v1/authorizations/lease-relationships:batch-check` | Maintenance/Report 批量验证 subject、lease、property 关系和 Lease 状态 |
| `POST /internal/v1/authorizations/report-generation:check` | 验证 tenant 的唯一当前租约是否为 active 且指向指定 property；executed 待入住拒绝 |
| `POST /internal/v1/privacy/subject-deletions:check` | 返回 pending_signature/executed/active lease blockers；Identity 删除前 fail-closed 检查 |
| `POST /internal/v1/privacy/subject-deletions/{request_id}` | Identity deletion worker 幂等删除 subject 的 party、case、申请、合同、账单、消息和关联，完成后 acknowledgement |

Subject 删除是正常永久历史保留的唯一产品例外。删除事务按 FK 顺序执行并先阻止新写；若正式
部署策略要求合同留存，则合同/账单不可逆匿名化，不能保留可回推 subject 的映射。任何部分失败
保持 deletion request 未完成并可重试。

## 11. 事件

| 事件 | 触发点 | 关键 payload |
|---|---|---|
| `property.status_changed.v1` | 房源发布/占用/恢复 | `property_id,status,visibility,version` |
| `prospect.case_changed.v1` | stage/assignment 变化 | `case_id,stage,status,assigned_staff_id,version` |
| `application.decided.v1` | approved/rejected | `application_id,case_id,property_id,status,version` |
| `application.invalidated.v1` | 其他租约执行后的自动收口 | `application_id,customer_subject_id,previous_status,status=ineligible|expired,closed_reason=another_lease_executed,closed_at,winning_lease_id,assigned_staff_id,version` |
| `lease.executed.v1` | 租约执行事务 | `lease_id,property_id,customer_subject_id,starts_on,ends_on,lease_version` |
| `lease.cancelled.v1` | 执行前取消 | `lease_id,property_id,customer_subject_id,reason_code,cancelled_at` |
| `lease.expired.v1` | 待签报价过期 | `lease_id,property_id,customer_subject_id,offer_expires_at,expired_at` |
| `lease.activated.v1` | 到达起租日 | `lease_id,property_id,customer_subject_id,starts_on` |
| `lease.ended.v1` | 正常结束 | 同上 + `ended_at` |
| `lease.terminated.v1` | 提前终止 | 同上 + `reason_code` |
| `customer.tenancy_status_changed.v1` | 租约执行或结束/终止事务 | `event_id,customer_subject_id,lease_id,to_status=tenant|former_tenant,aggregate_version,occurred_at` |

`customer.tenancy_status_changed.v1` 使用按 customer 单调递增的 aggregate_version。租约执行发布
`to_status=tenant`；结束/终止发布 `to_status=former_tenant`。Identity 只消费客户阶段投影，事件
不携带租约 count；承租关系、Lease 状态和唯一槽位真相始终属于本服务。

## 12. 错误码、并发和缓存

错误结构和 HTTP 映射遵循 [统一错误契约](README.md)。本服务关键子码：
`property_not_visible`、`prospect_case_not_found`、`case_access_denied`、
`application_state_conflict`、`lease_state_conflict`、`lease_signature_incomplete`、
`lease_terms_changed`、`lease_date_overlap`、`customer_not_eligible_for_lease`、
`customer_already_has_lease`、`application_superseded`、`application_already_has_lease`、
`property_no_longer_available`、`lease_offer_expired`、`lease_slot_mismatch`、
`lease_activation_not_due`、`lease_end_not_due`、`lease_access_required`、`version_conflict`、
`idempotency_conflict`、`dependency_unavailable`、`dependency_timeout`。

- 私有对象不存在或无权访问统一 HTTP 404；本服务内部可保留不同诊断子码，但 Portal 面向浏览器
  必须统一为 `resource_not_found`。已确认资源可见但动作被角色/阶段禁止才返回 403。
- 房源/租约/申请可变聚合使用 version/ETag；写命令保存幂等记录或建立业务唯一约束。
- 公开房源 cache-aside TTL 30–120s + jitter，状态事件主动失效。
- Staff 列表 key 包含 staff ID、role version、scope version 和过滤 hash，TTL ≤30s。
- Lease 动作授权默认回源；若缓存，key 必须包含 subject、lease、action、lease version 与
  relationship version，Lease 状态或承租关系变化时立即失效。
- Redis 不可用时公开读回源；合同执行不得因缓存不可用而跳过检查。
- `leases.application_id` 唯一冲突、customer slot 唯一冲突和 property/date EXCLUDE 必须分别映射为
  `application_already_has_lease`、`customer_already_has_lease`、`lease_date_overlap`，不得返回 SQL。

## 13. 首批契约测试

1. Guest 永远无法从市场 API 获得 private/staff 字段。
2. Customer A 无法读取 Customer B 的 case、message、application、lease 或 invoice。
3. 重发 contact/message/application/sign/execute 命令不产生重复数据。
4. 未全部签署、terms digest 不一致或租期重叠时不能执行。
5. 执行事务失败不会留下错误的 lease/slot、converted case 或 outbox 部分状态。
6. Staff permission 与资源 scope 缺一不可；知道 public ID 不增加访问权。
7. `lease.executed` 至少一次重复投递时消费者结果保持唯一。
8. 两个并发待签请求只有一个能占用 customer lease slot；tenant 无法申请或签署第二份租约。
9. 合同执行前 customer 仍为 prospect/former_tenant；执行后才发布 tenant 状态事件。
10. 创建 lease 时承租人只能从 approved application 推导，传入或伪造 tenant_subject_id 被协议层拒绝。
11. 两个 customer 并发签订同一 property 的重叠租期时，数据库 exclusion constraint 最多允许一个成功。
12. cancel/expire/end/terminate 重复执行幂等释放 slot；自然结束后本人按历史承租关系只读并发布 former_tenant。
13. 一份租约执行后，该 customer 的其他申请、case 和未占 slot draft lease 全部按规则收口。
14. 撤回 approved application 会原子取消其 draft Lease；pending signer 拒签、员工取消或报价过期
    会同步关闭 application/case、释放 slot 并恢复正确 property availability，不留下孤立 draft 或
    永久 under_offer 状态。
