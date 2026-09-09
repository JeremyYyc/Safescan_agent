# Tenant Portal API（BFF）

> 状态：目标契约；待实现
> 用户：guest、prospect、tenant、former_tenant
> 数据所有权：无业务表
> 容器监听端口：`8007`；对应 React：`tenant-web:80`，Gateway 页面前缀 `/tenant/`

## 1. 定位

Tenant Portal API 是客户侧页面 BFF。它为公开房源、本人潜客流程、申请、合同、维修和本人租期报告
提供稳定、强脱敏的页面投影。它不是前端代码，不拥有租赁、维修、报告数据，也不经过
Tenant Agent。

外部前缀 `/api/v1/tenant`。注册、登录、refresh、logout 和 `/me` 由 Gateway 直达 Identity。
React 固定包含 Topbar 和侧边栏；一级菜单为“房源信息、我的申请、我的房子、Agent”。“我的
房子”对 tenant/former_tenant 展示：Tenant 看到当前合同、property 报告、缴费记录和维修入口；
Former Tenant 只看到历史租约/房产及对应历史报告。

## 2. 身份能力矩阵

| 能力 | Guest | Prospect | Tenant | Former tenant |
|---|---:|---:|---:|---:|
| 浏览公开房源 | ✓ | ✓ | ✓ | ✓ |
| 联系真人业务员 | 登录后 | ✓ | ✓ | ✓ |
| 创建租房申请 | — | ✓ | —（历史只读） | ✓ |
| 查看/签署本人合同 | — | 待签 applicant/signer 关系 | 本人当前/历史承租关系 | 待签 applicant/signer 关系或本人历史承租关系 |
| 创建维修工单 | — | — | 本人 Lease active | — |
| 查看维修历史 | — | — | 本人当前承租关系 | 账号存续期间的历史承租关系 |
| 为房产生成报告 | — | — | 仅唯一 active 租约 property | — |
| 查看报告 | — | — | 报告 source_lease_id = 本人 active Lease | 仅从历史租约房源详情查看该 source_lease_id 报告 |
| 使用 Agent | — | ✓ | ✓ | ✓ |

`customer_status` 只决定基础功能上限，不是具体资源授权。

## 3. API

### 3.1 Bootstrap 与首页

| 方法与路径 | 下游 | 返回 |
|---|---|---|
| `GET /api/v1/tenant/bootstrap` | Identity me/permissions | customer、status/version、导航能力；guest 返回公开能力 |
| `GET /api/v1/tenant/home` | Leasing + Maintenance + Report | 当前申请、有效租约、open 工单、本人可访问报告摘要 |
| `GET /api/v1/tenant/topbar` | Identity | username、customer status、profile/session 菜单 |

首页非关键模块可返回 `partial_errors`，但绝不能因为某下游失败而把用户展示成“没有合同”或
“没有欠款”。这种无法区分空数据与失败的场景应展示模块暂不可用。

### 3.2 公开房源

| 方法与路径 | 请求/行为 |
|---|---|
| `GET /api/v1/tenant/properties` | `q? bedrooms? min_rent? max_rent? cursor? limit?`；公开投影 |
| `GET /api/v1/tenant/properties/{id}` | 公开详情、可租状态与联系 CTA |
| `POST /api/v1/tenant/properties/{id}/favorite` | P1；登录 customer |
| `DELETE /api/v1/tenant/properties/{id}/favorite` | P1；登录 customer |

未发布、非 marketing 或不可公开房源返回 404；响应不包含 owner、租客、内部状态、员工 scope、
已有申请人或内部备注。

### 3.3 联系业务员

| 方法与路径 | 请求/行为 |
|---|---|
| `POST /api/v1/tenant/properties/{id}/contact` | `message,client_message_id`；登录 customer；创建/复用 case/thread |
| `GET /api/v1/tenant/prospect-cases` | 本人的 cases |
| `GET /api/v1/tenant/prospect-cases/{id}` | 本人 case 与业务员公开资料 |
| `GET /api/v1/tenant/contact-threads/{id}/messages` | 本人线程，cursor/after_sequence |
| `POST /api/v1/tenant/contact-threads/{id}/messages` | `content,client_message_id`；幂等 |

首条联系若业务员暂未分配仍返回已受理 case，不伪造员工。真人线程与 Agent 对话完全分离。

### 3.4 看房与申请

| 方法与路径 | 请求/行为 |
|---|---|
| `GET /api/v1/tenant/properties/{id}/viewing-slots` | P1 可预约时段 |
| `POST /api/v1/tenant/viewings` | P1 创建预约；幂等键 |
| `GET /api/v1/tenant/viewings` | P1 本人预约 |
| `POST /api/v1/tenant/applications` | `case_id,property_id,desired_start_on,term_months,occupants,note?` |
| `GET /api/v1/tenant/applications` | 本人申请列表 |
| `GET /api/v1/tenant/applications/{id}` | 本人申请详情和公开决策状态 |
| `PATCH /api/v1/tenant/applications/{id}` | 仅 draft，携带 version |
| `POST /api/v1/tenant/applications/{id}/submit` | `attestation=true,version`；幂等键 |
| `POST /api/v1/tenant/applications/{id}/withdraw` | 非终态撤回 |

内部审核 note、评分和其他申请人信息永不返回客户投影。
创建、编辑和提交只允许 prospect/former_tenant；tenant 调用写接口返回
`403 customer_not_eligible_for_lease`，但可读取全部本人历史申请。

### 3.5 合同和账单

| 方法与路径 | 请求/行为 |
|---|---|
| `GET /api/v1/tenant/leases` | 本人待签、executed、active 和账号存续期间永久保留的历史租约 |
| `GET /api/v1/tenant/leases/{id}` | applicant/signer/本人承租关系验证后的客户 LeaseView |
| `POST /api/v1/tenant/leases/{id}/signature` | `lease_document_id,terms_digest,accepted=true,version`；只能本人签 |
| `POST /api/v1/tenant/leases/{id}/decline` | `reason_code,version`；本人 pending signer 拒绝待签合同并触发取消/释放 slot |
| `GET /api/v1/tenant/leases/{id}/document` | 合同只读内容；短期受控下载/HTML |
| `GET /api/v1/tenant/leases/{id}/invoices` | 本人承租关系；cursor |
| `GET /api/v1/tenant/my-property` | tenant 当前唯一租约对应 property、合同、缴费、维修和报告摘要 |
| `GET /api/v1/tenant/rental-history` | 本人 ended/terminated Lease 与历史 property 摘要；Tenant/Former Tenant |
| `GET /api/v1/tenant/leases/{id}/property` | 本人历史 Lease 对应 property、合同、缴费和报告入口；只读 |

BFF 不生成签名时间，不允许客户端提交 subject/party/signer ID。执行前通过
application applicant/lease signer 关系读取和签署，执行后通过本人承租关系读取；服务从 token
subject 推导当前签署人。条款 digest 与当前合同不一致返回 409，要求重新确认最新合同。
历史合同在账号正常存续期间永久保留；账号删除按 Identity deletion request 跨服务清理。
`/tenant/my-property` 页面在 Tenant 状态显示当前房产并附带历史列表，在 Former Tenant 状态只显示
`rental-history`；Prospect 不显示该菜单。历史详情的 lease ID 必须先验证本人承租关系。

### 3.6 维修

| 方法与路径 | 请求/行为 |
|---|---|
| `POST /api/v1/tenant/maintenance-orders` | `summary,description?,priority`；幂等键；BFF 从本人唯一 active Lease 推导 lease/property |
| `GET /api/v1/tenant/maintenance-orders` | 本人租约关联工单 |
| `GET /api/v1/tenant/maintenance-orders/{id}` | 客户投影 + 脱敏时间线 |
| `PATCH /api/v1/tenant/maintenance-orders/{id}` | open 且未处理时允许字段 |
| `POST /api/v1/tenant/maintenance-orders/{id}/comments` | public comment + client_message_id |
| `POST /api/v1/tenant/maintenance-orders/{id}/cancel` | 仅允许的早期状态，version |

BFF 不仅检查 `customer_status=tenant`；Maintenance 必须向 Leasing 校验 lease.status=active 和
Lease/property 归属关系。浏览器提交的 `lease_id/property_id/subject_id` 视为协议校验失败，不得用于
授权。executed 待入住阶段返回 `403 action_forbidden`，到 starts_on 激活后才开放。

### 3.7 Property 视频报告

| 方法与路径 | 请求/行为 |
|---|---|
| `GET /api/v1/tenant/my-property/reports` | 当前唯一 active 租约 property 的本人可见报告；executed 待入住阶段拒绝 |
| `POST /api/v1/tenant/my-property/reports` | `title?`；创建绑定当前 property/source lease 的 draft report |
| `POST /api/v1/tenant/reports/{id}/files/videos` | raw `video/*`；流式代理，报告创建者本人 |
| `POST /api/v1/tenant/reports/{id}/jobs` | `input_file_id,attributes{}`；幂等键，返回 202/job ID |
| `GET /api/v1/tenant/report-jobs/{id}` | 查询持久任务状态 |
| `GET /api/v1/tenant/report-jobs/{id}/events` | SSE/NDJSON，支持 after_sequence 恢复 |
| `GET /api/v1/tenant/leases/{lease_id}/property/reports` | 历史租约对应房源详情下的报告列表；Former Tenant 只读入口 |
| `GET /api/v1/tenant/reports/{id}` | tenant 脱敏投影；必须由当前“我的房子”或本人历史 lease/property 关系授权 |

创建报告时 BFF 不接受客户端提交 property_id、lease_id 或 subject_id，而是从当前唯一租约投影
得到并传给 Report Service。Report Service 必须再次回查 Leasing，验证
`tenant + unique current lease + lease.status=active + lease.property_id`；executed 待入住阶段不得
创建。成功创建时由 Report Service 自动写入当前唯一 `source_lease_id`。P0 不提供共享、owner、
ACL、报告删除或 Tenant 下载接口。
报告直接依附 property，不返回旧 chat_id/legacy_context_id。Customer 侧只有 Tenant 可以从
“我的房子”发起生成并查看当前租约房源报告；Prospect 无报告入口。Former Tenant 只能先进入本人
历史租约对应的历史房源详情，再读取 `source_lease_id` 等于该历史 Lease 的报告；
不能下载、修改、分享、删除或为历史房产新建报告。公开房源详情和全局报告列表不得暴露历史报告。

### 3.8 Agent 入口

`/tenant/agent` 对已登录 prospect/tenant/former_tenant 展示。Agent 不参与确定性租赁主链路；
本 BFF 只提供导航/bootstrap，Agent 会话接口由独立 tenant-agent-service 负责。

## 4. Identity 使用逻辑

1. 未登录访问公开房源不要求 guest session，Guest 不在 Identity 中创建账号。
2. 注册调用 `/api/v1/auth/register`，固定成为 customer/prospect。
3. 登录统一调用 `/api/v1/auth/login`；只接受返回的 `portal`，不传角色选择。
4. Access token 仅保存在内存；页面冷启动调用 refresh，然后 bootstrap。
5. refresh/logout 使用 HttpOnly cookie + CSRF header；401 时最多单飞刷新一次，防止并发 refresh
   rotation 被多个请求重复消费。
6. `token_stale` 或 customer status 变化后刷新 token并重载 bootstrap；不得仅修改前端状态。

## 5. 错误和隐私

- 所有错误遵循 [统一错误契约](README.md)。私有资源不存在、无权或不可见时，BFF 面向浏览器
  一律返回 `404 resource_not_found` 和空 details；领域内部的 `property_not_visible`、
  `case_access_denied`、`lease_access_required`、`report_access_denied` 等原始子码仅写服务端日志。
  登录缺失返回 401；已经确认资源属于本人但客户阶段禁止动作时返回 403。
- 浏览器可保留的领域稳定 code：`application_state_conflict`、
  `customer_not_eligible_for_lease`、`customer_already_has_lease`、
  `application_superseded`、`application_already_has_lease`、`lease_terms_changed`、
  `lease_offer_expired`、`order_state_conflict`、
  `active_lease_blocks_deletion`、`open_maintenance_orders_block_deletion`、
  `report_generation_not_allowed`、`current_lease_required`、`active_job_exists`、`file_not_ready`、
  `version_conflict`、`idempotency_conflict`。
- 前端 message 本地化，但不得把下游堆栈、对象 key、其他用户 ID 和内部 decision note 返回。
- 聚合失败用 `partial_errors` 明示，不以空数组伪装成功。
- 除私有资源 404 必须归一化外，BFF 不把领域子码改写为通用 `state_conflict`；数据库/依赖异常
  只接受领域服务已完成的安全映射。

## 6. 缓存与限流

- 公开房源：CDN/Redis 30–120s + ETag + stale-while-revalidate；发布状态事件主动失效。
- `tenant:bootstrap:{subject}:{auth_version}:{customer_status_version}`：≤30s。
- Tenant home：5–15s；key 含 subject、Lease/relationship version 与 report version；不得跨 subject 共享。
- 私有合同/工单/报告详情默认短缓存 5–15s；写后主动删除。
- 不缓存 401/403、签署响应、Lease/报告访问判定和短期下载 URL。
- Redis 限流至少覆盖：guest/session、register/login、contact message、application submit、
  maintenance create/comment 与文件下载。
- Access token 过期并发时使用 single-flight refresh；服务端 refresh rotation 仍是最终真相。

## 7. 契约测试

1. Guest 只获得公开房源投影，无法调用 contact/application/lease/maintenance/report 私有 API。
2. Customer 之间 case、message、application、lease、order、report 完全隔离。
3. Prospect 没有本人 active Lease，即使伪造 status/property ID 也不能报修。
4. 签署人从 token 推导，不能代签；旧 terms digest 不能签署。
5. Tenant 只能为当前唯一租约 property 创建报告；Prospect/Former Tenant 和伪造 property 均拒绝。
6. 当前 Tenant 可从“我的房子”生成/查看；Former Tenant 只能从历史租约房源详情只读查看，且不能
   通过公开房源或全局列表枚举历史报告。
7. 并发 401 只触发一次 refresh；重放旧 refresh token 不产生新的 session。
8. Redis 故障不造成跨用户缓存泄漏或授权 fail-open。
9. Pending signer 可通过 applicant/signer 关系读取合同；既非 applicant/signer 又非承租人的其他 customer 返回 404。
10. decline 重复提交幂等取消待签合同、释放 slot，且不把 prospect/former tenant 改成 tenant。
11. 租约结束后 Former Tenant 仍可经历史 Lease 只读查看同一 `source_lease_id` 报告，不能下载或修改。
12. 对同一私有资源路由，随机不存在 ID 与另一客户真实 ID 的浏览器响应均为相同
    `404 resource_not_found`、空 details，不能从 code/message/body 长度判断资源存在性。
13. 租户报修请求不接受浏览器提供 lease/property/subject ID；BFF 和领域服务从本人唯一 active
    Lease 推导并复核，防止参数篡改。
