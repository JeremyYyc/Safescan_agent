# SafeScan 非 Agent 全业务 MVP PRD

> 版本：v1.4
> 日期：2026-09-09
> 状态：P0 文档冻结基线；下一阶段按本文实现代码
> 范围：双 React 前端、双 Portal API、领域微服务与现有视频报告迁移；Agent 菜单仅预留入口

## 1. 执行摘要

SafeScan 当前已经具备独立 Identity 服务、目标数据库 schema 和可运行的视频报告旧业务，但
房源、潜客、租赁、维修以及双 Portal 仍未形成可端到端验收的产品闭环。本期建设一个不依赖
Agent 的最小租赁业务平台，让用户可以通过确定性页面完成：员工登录、客户注册／登录、浏览
房源、联系真人业务员、申请租房、双方签订合同、租约生效、租客报修，以及当前租客或有权
员工基于房屋视频生成安全报告。报告的业务父实体由旧 `chat` 改为 `property`。

本期采用 Portal API（BFF）承接页面契约，领域微服务拥有业务规则和数据。视频报告继续调用
现有 `backend/app` 中已经运行的上传、LangGraph 分析、持久任务、MinIO 与 PDF 逻辑；迁移只
增加适配器和访问授权，不重写提示词、模型调用、抽帧、评分、验证或 PDF 生成逻辑。

## 2. 产品目标与成功指标

### 2.1 目标

1. 在不调用 Staff Agent 或 Tenant Agent 的情况下跑通完整主链路。
2. 复用已实现的 Identity 注册、登录和 refresh 能力，并初始化 12 个可直接登录的员工账号。
3. 建立清晰的 Portal／领域服务边界，任何业务事实只有一个数据所有者。
4. 将旧视频报告能力以兼容方式接入租赁业务，并最终迁入 inspection-report-service。
5. 给出可直接进入开发的 HTTP 契约、状态机、权限、缓存和验收标准。

### 2.2 MVP 成功指标

| 指标 | 目标 |
|---|---|
| P0 主链路 E2E | 100% 自动化通过 |
| 普通聚合查询延迟 | P95 ≤ 500ms，P99 ≤ 1s（不含视频处理） |
| 单领域普通命令延迟 | P95 ≤ 800ms |
| 登录接口延迟 | P95 ≤ 800ms（含 Argon2id 校验） |
| API 可用性 | 月度 ≥ 99.9% |
| 非预期 5xx | < 0.5% |
| 重复写入 | 相同主体与幂等键下为 0 |
| 越权数据泄漏 | 0；IDOR 契约测试 100% 通过 |
| 报告任务可靠性 | API/SSE 断开或 API 重启不丢任务、不重复生成报告 |

## 3. 用户与角色

| 用户 | 主要目标 | MVP 权限边界 |
|---|---|---|
| Guest | 浏览公开房源 | 只读 `public + marketing` 投影，不能联系业务员或读取私有数据 |
| Prospect customer | 联系业务员、提交租房申请 | 只能访问自己的 prospect case、联系线程和申请 |
| Tenant customer | 查看合同、报修、为当前房产生成/查看报告 | 同时只能有一个当前租约；具体权限由本人承租关系、Lease 状态和资源归属共同决定 |
| Former tenant | 查看历史合同／报告，再次找房 | 合同正常账户生命周期内永久保留；报告在租约结束后降为只读 |
| Leasing consultant | 接洽潜客、审查申请、准备和签署合同 | 市场房源 + 分配给自己的 case；不能默认读取在租隐私 |
| Property manager | 管理负责房源、维修、检查和报告 | 必须同时具备 permission 和 building/property scope |
| Maintainer | 处理分配给自己的维修工单 | 只见完成工作所需的房源、联系人与报告片段 |
| Manager admin | 管理员工、角色和全局业务 | 可查看全部租约双方详情和全部维修工单；仍须遵守状态机、版本和审计 |

一个邮箱只对应一个账号，账号固定为 `staff` 或 `customer`。登录后由 Identity 返回
`portal=staff|tenant`，前端不提供身份切换器。

员工端 P0 菜单按职责裁剪：Leasing Consultant 使用房源和“我的订单”；Property Manager 使用
负责楼栋房源、维修工单和报告生成；Maintainer 使用本人维修工单及工单所需房源上下文；Manager
Admin 查看全部楼栋、全部租约双方详情、全部维修工单、员工账号与权限，并可生成报告。Agent
入口对全部 active staff 展示，但业务实现不在本期。
准确 permission code 及角色 seed 以 Identity API 契约为准。

## 4. 范围

### 4.1 P0 范围

- Guest 浏览公开房源列表和详情。
- Customer 自助注册、登录、刷新、退出和查看本人资料。
- Identity 初始化 4 名 Leasing Consultant、4 名 Property Manager、3 名 Maintainer 和 1 名 Manager Admin；员工直接登录，不做邮件激活。
- Customer 针对房源建立潜客案件并联系真人业务员。
- Leasing consultant 查看分配案件、回复消息、推进案件阶段。
- Prospect/Former Tenant 创建并提交租房申请；业务员审核并批准／拒绝。
- 业务员为已批准申请准备租约；租客签署、公司签署并执行租约。
- 客户同时最多拥有一个待签/已执行/有效租约；只有 prospect/former tenant 可申请并签约。
- `customer.tenancy_status_changed.v1` 事件在租约执行后驱动 Identity 将 customer 更新为 tenant。
- Tenant 查看本人合同和基础账单投影。
- Manager Admin 查看员工账号/权限、全部租约双方详情和全部维修工单。
- Tenant 对有效租约房源创建维修工单、查看进度、补充说明。
- Property manager 分派工单；Maintainer 推进工单到完成。
- Property Manager/Manager Admin 可为有权房源生成报告；Tenant 可为本人当前租住房产生成报告。
- 每份报告必须直接关联一个 property；租客可见报告还必须绑定 `source_lease_id`，以本人承租关系
  和 Lease 状态隔离不同租期用户。
- 所有写命令具备幂等、乐观锁或数据库唯一约束；所有敏感访问做资源级授权。

### 4.2 P1 范围

- 看房预约、收藏、PDF 导出、在线付款和账单文件下载；P0 仅提供合同金额、账单/缴费记录只读投影。
- 邮箱验证、密码找回、设备会话管理。
- 员工账号增删改、邮件激活和资源 scope 变更页面；P0 只要求 Manager Admin 可查看账号与权限。
- Manager Admin 业绩、月度销售统计和分析页面。
- 报告生成实时进度恢复、失败重试展示。
- Contact、维修和合同状态的站内通知。

### 4.3 不在本期范围

- Staff Agent、Tenant Agent、自然语言任务编排和 A2A。
- 在线支付、退款和财务对账；MVP 仅提供账单只读投影。
- 第三方具有法律效力的电子签章、实名核验和合同模板编辑器。MVP 签署是带审计记录的
  产品确认流程，正式商用前必须接入合规电子签平台。
- 自动信用检查、租客背景调查、复杂联合承租审批。
- 视频分析算法、提示词、模型、抽帧、评分和 PDF 版式重写。
- 多公司／多组织切换。

## 5. 信息架构与页面骨架

### 5.1 租户／潜户 React 服务（`tenant-web`）

```text
/tenant/login                登录
/tenant/register             客户注册
/tenant/properties           房源信息；详情内联系业务员
/tenant/applications         我的申请；tenant 仅查看历史
/tenant/my-property          我的房子：Tenant 当前房产；Former Tenant 历史租住信息
/tenant/agent                Agent 预留入口
/tenant/profile              Topbar 中的个人资料与会话
```

所有页面共用侧边栏和 Topbar。Guest 不登录即可访问 `/tenant/properties`，其他页面要求 customer
登录；根据 prospect/tenant/former_tenant 裁剪菜单内容和动作。“我的房子”对 Tenant/Former Tenant
展示，Former Tenant 只能进入本人历史租约对应的只读房源详情。

### 5.2 员工 React 服务（`staff-web`）

```text
/staff/login                 登录
/staff/properties            按角色裁剪的房源信息
/staff/orders                潜客、申请、待签订单和历史合同
/staff/maintenance           Property Manager/Maintainer/Manager Admin 工单
/staff/admin/staff           Manager Admin 查看员工账号、角色和权限
/staff/agent                 所有员工的 Agent 预留入口
/staff/profile               Topbar 中的个人资料与会话
```

所有页面共用侧边栏和 Topbar；主页面随侧边栏选择切换。Manager Admin 的“我的订单”和“维修工单”
分别显示全局租约双方详情和全局工单双方详情，并增加只读的员工账号/权限入口；P0 不展示业绩或
月度销售。Property Manager/Manager Admin 从房源详情进入视频报告生成，Leasing
Consultant/Maintainer 不显示生成入口。

## 6. 端到端主流程

### 6.1 员工初始化与登录

1. Alembic 先初始化四种系统角色、权限和 Identity 表。
2. 非生产环境的 `identity-seed` 幂等创建 12 个约定员工；user 和 employment 均直接为 active。
3. 员工邮箱使用 `{FirstName}Safescan@outlook.com`，username 使用 `FirstNameLastName`。
4. 初始化明文密码只作为 seed 输入，数据库仅保存与 Identity 登录一致的 Argon2id 摘要。
5. 员工调用统一登录接口，Identity 返回 `portal=staff`、短期 access token 和 HttpOnly refresh cookie。
6. 前端只在内存保存 access token并跳转 `/staff/`；刷新页面通过 refresh cookie 换取 token。

种子人员固定为：Leasing Consultant（Ethan Carter、Olivia Bennett、Liam Foster、Sophia Reed）、
Property Manager（Noah Mitchell、Emma Collins、James Parker、Ava Richardson）、Maintainer
（Daniel Cooper、Grace Turner、Henry Walker）、Manager Admin（Charlotte Morgan）。每人的准确
staff code、username、email 和初始化密码以
[Identity API 的种子清单](backend/api/identity-access-api.md#143-staff-初始化与首次使用)为唯一契约。

验收：未初始化、suspended、ended employment 或 disabled role 均不能登录；连续五次密码失败
锁定 15 分钟；角色或雇佣状态变化使旧 token/session 失效。

为保证空库能够直接跑通 P0，非生产 `domain-seed` 还需幂等创建最小演示数据：4 栋 building、
每栋至少 2 套 public/marketing 空置 property，并分别给 4 名 Property Manager 分配一个 building
scope。Leasing Consultant 通过市场房源和 case assignment 工作，不需要复制 property scope；
Manager Admin 使用全局权限。seed 只用于本地/测试/演示，生产环境默认关闭。
主链路 E2E 使用可注入时钟和 `starts_on=测试当天`，执行一次 lifecycle worker tick 将 executed
推进为 active，再继续维修与报告步骤；测试不得依赖真实等待跨日。

### 6.2 客户注册、登录与浏览房源

1. Guest 无 Identity 账号和租客身份，不登录即可浏览公开房源。
2. 公开列表只返回 `listing_visibility=public` 且处于 `marketing` 的可租投影。
3. 注册固定创建 `account_type=customer`、`customer_status=prospect`，客户端不能提交身份字段。
4. 登录响应返回 `portal=tenant`；tenant/former tenant 仍可继续浏览公开房源。

### 6.3 联系真人业务员

1. 登录 customer 在房源详情点击“联系业务员”并发送首条消息。
2. Property Leasing 在同一事务中获取／创建唯一 party、创建或复用该客户针对该房源的 open
   prospect case、选择业务员、创建 active contact thread、写首条消息与 case event。
3. 重复提交以 `client_message_id` 去重，返回同一消息结果。
4. Leasing consultant 在员工工作队列看到分配案件并回复。
5. 案件改派时同步更新 active thread 的业务员并写事件；旧业务员立即失去访问权。

MVP 要求登录后才能联系真人，避免 guest subject 与正式 CRM 主体混用。匿名联系方式属于
后续营销线索能力。

P0 业务员选择使用简单的稳定散列：按 staff public ID 排序 active Leasing Consultant，以
`hash(customer_subject_id,property_id)` 取模选择。若列表为空或选中员工在提交前已失效，
case/thread/首条消息仍成功保存并标记 unassigned，由 Manager Admin 后续改派；不引入负载统计、
跨服务锁或独立调度服务。

### 6.4 租房申请

当前基础流程是：customer 联系某套房源形成 case，在 case 下创建 draft，提交后由负责业务员
执行 `submitted → reviewing → approved|rejected`，approved 申请再用于准备合同。当前模型只限制
同一 case/property 不存在多个非终态申请，允许同一客户同时申请不同房源；原设计没有定义其中
一份合同执行后其他申请如何结束。

P0 优化后的完整流程：

1. 只有 prospect/former tenant 可从自己的 open case 对目标房源创建 draft；tenant 只能查看历史。
2. Customer 补齐期望入住日、租期、入住人数和说明；敏感证件材料不在 P0。
3. Customer 提交后执行 `draft → submitted` 并记录 `submitted_at`；业务员执行
   `submitted → reviewing → approved|rejected`。
4. 同一客户可以并行申请不同房源，但同一 case/property 只能有一个非终态申请；全部更新携带
   version。
5. approved 将对应 case 推进至 negotiation，但不会自动执行租约。
6. 某份租约执行成功时，Property Leasing 在同一事务内收口该客户的其他流程：
   - 其他 `draft/submitted/reviewing` application → `ineligible`；
   - 除获胜 application 外，所有其他 `approved` application → `expired`，无论是否已经生成 draft lease；
   - 其他 approved application 已经生成非终态 draft lease 时，对应 draft lease 同时 → `cancelled`；
   - 自动失效的 application 写入 `closed_reason=another_lease_executed`、`closed_at` 和
     `winning_lease_id`；
   - 获胜 case → `converted/closed`，其他 open case → `lost/closed`；
   - 每项写 application/case event，并在同一事务写 outbox。
7. outbox 发布 `application.invalidated.v1`/`prospect.case_changed.v1`，相关 Leasing Consultant 的
   “我的订单”显示状态变化；实时弹窗通知仍为 P1，但 P0 页面刷新后必须可见。
8. 自动收口事件重复消费不得重复改变状态；执行事务失败时租约、slot、申请和 case 全部回滚。
9. Customer 主动撤回 `draft/submitted/reviewing` 申请时，申请变为 `withdrawn`；撤回已批准但仅生成
   `draft` lease 的申请时，申请、draft lease 和对应 case 在同一事务分别变为
   `withdrawn/cancelled/lost+closed`。已经进入 `pending_signature` 后不得绕过合同状态机直接撤回
   application，必须使用拒签；拒签原子取消 Lease、释放 slot、把申请标记为 `withdrawn` 并关闭 case。

### 6.5 准备、签署和执行合同

1. 具备 `lease:prepare` 的业务员只提交 approved `application_id` 和合同业务条款。Property Leasing
   必须从 `application → applicant party → subject_id` 推导唯一承租人；请求不得接受
   `tenant_subject_id`。
2. 服务锁定 property、customer party 和唯一 `customer_lease_slot`；只有 prospect/former tenant
   且不存在其他 pending_signature/executed/active slot 才能进入待签。
   `draft` 只是员工内部准备的合同草稿，不代表客户当前租约且不占 slot；同一客户即使因多个
   approved application 存在多个 draft，也只有一个能原子进入 pending_signature，其余在获胜
   Lease 执行时按第 6.4 节取消。
3. 业务员确认条款后生成不可变 lease document（document ID、版本和内容摘要），再将租约置为
   `pending_signature`。进入待签后不得原地覆盖条款；修改条款必须生成新版本并使旧待签失效。
4. 唯一租客只可代表自己确认签署；记录 `lease_tenants.signed_at`、IP/UA 哈希、条款摘要
   与 lease document ID。不得由 Portal 代填签署时间。
5. 具备权限的员工执行公司签署，记录 `company_signed_at`。
6. 全部必签租客与公司都已签署后，业务员显式执行合同。
7. Property Leasing 在一个事务内设置 `executed_at/status`、把 lease slot 更新为 executed、转化
   prospect case、更新房源状态并写 outbox。目标设计删除独立 Lease Grant；承租关系以
   `lease_tenants → parties.subject_id` 为准。
8. Property Leasing 发布 `customer.tenancy_status_changed.v1(to_status=tenant,
   aggregate_version)`；Identity 幂等消费并递增授权版本。事件不携带或依赖租约数量；一个客户
   同时只有一个当前租约由 Property Leasing 的数据库 slot 唯一约束保证。
9. PostgreSQL 使用 `btree_gist + EXCLUDE` 约束，禁止同一 property 的
   `pending_signature/executed/active` 租期发生日期重叠；应用层 property 行锁只作为友好错误和
   串行化手段，数据库约束是最终保护。
10. 生命周期规则：
    - `draft|pending_signature → cancelled`：有权员工取消；pending tenant 可显式拒绝；释放 slot；
    - `pending_signature → expired`：超过 `offer_expires_at` 后由 lifecycle worker 执行；释放 slot；
    - `executed → active`：达到 `starts_on` 后由 lifecycle worker 执行；customer 已在 execute 时成为 tenant；
    - `executed|active → ended`：到达 `ends_on` 后自然结束并释放 slot；
    - `executed|active → terminated`：提前终止并释放 slot。
11. `cancelled/expired` 发生在执行前，不改变 prospect/former tenant 身份；`ended/terminated` 发布
    `to_status=former_tenant`。worker 重跑、人工补偿和事件重放均须幂等。
    待签拒签时关联 application 变为 `withdrawn`；员工取消或报价过期时关联 application 变为
    `expired`。三种情况都关闭对应 case，并在同一事务释放 slot、重新计算 property availability。
12. `executed` 表示合同已执行但尚未到起租日：Tenant 可查看合同和待入住房产，但不能创建维修
    工单或视频报告。只有达到 `starts_on` 且 lease 已转为 `active` 后才开放这两项能力；P0 不支持
    提前交接，未来如需要使用独立 `early_access_from` 字段和状态规则，不改变 `starts_on` 语义。

历史合同在账号正常存续期间永久保留并只读。客户申请删除账号是唯一例外，进入第 6.8 节的
跨服务删除流程。

### 6.6 租客申请维修与员工处理

1. Tenant 选择本人 `lease.status=active` 且 `lease_tenants → parties.subject_id` 命中本人的租约和房源，提交问题
   摘要、描述和优先级；`executed` 但尚未到 `starts_on` 的租约不能报修。
   图片附件为 P1，不是本期主链路完成条件。
2. Maintenance 回查 Property Leasing 的 lease/property 最小授权投影。
3. 在一个事务内创建正式工单、首条 `reported` 事件和 outbox；相同幂等键返回原结果。
4. Property manager 只能在有效 scope 内分派给 active maintainer。
5. Maintainer 只能对分配给自己的工单执行允许的状态迁移并添加工作记录。
6. Tenant 可查看脱敏时间线，但不能看到内部成本、内部备注或其他租客信息。

状态机：

```text
open → assigned → in_progress → blocked → in_progress → completed
  └──────────────────────────────→ cancelled
```

完成与取消为终态；每次迁移都要求 `version`、写只追加事件并记录 actor。

### 6.7 双端视频报告生成与访问

1. Property Manager/Manager Admin 为有权房源，或 Tenant 为本人当前租住房产创建 property report job。
2. 浏览器经对应 Portal 上传原始 `video/*` body；Portal 流式转发，不将完整视频读入内存。
3. Inspection Report 保存私有 MinIO 对象和文件元数据。
4. 创建持久 `report_job` 并立即返回 `202 + job_id`；worker 继续调用原有
   `WorkflowOrchestrator().execute_workflow(...)`。
5. 页面可通过 job 查询或事件流查看进度，断线后用 job ID 恢复。
6. 任务成功后把原有 report JSON、区域、证据图片、视频引用和 PDF 关系写入直接关联
   `property_id` 的 report；旧 chat ID 仅作为 adapter 内部 `legacy_context_id`。
7. Customer 侧只有 `lease.status=active` 的当前 Tenant 可以从“我的房子”发起报告生成并查看当前
   租约房源报告；`executed` 待入住 Tenant 与 Prospect 均不具有报告生成能力。租客生成时服务端
   自动记录当前唯一 `source_lease_id`，不接受浏览器提交 subject/property/lease ID。
8. Former Tenant 只能先进入某份历史租约对应的历史房源详情，再查看 `source_lease_id` 等于该
   历史租约的报告；不得从公开房源详情或全局报告列表发现报告，也不能创建、修改、分享、删除或下载。
9. 员工端沿用已确认规则：Property Manager/Manager Admin 可按 property scope 生成和查看报告，
   生成时由服务端读取该 property 的唯一 active Lease：存在时自动写 `source_lease_id`，报告同时对
   该租期 Tenant 可见；不存在时保存为 `source_lease_id=null` 的 staff-only property report。未来
   租客不会因为入住同一 property 自动看到旧报告。
10. Tenant Portal 必须同时满足本人 lease 关系、报告 `source_lease_id` 与 Lease 状态；员工端必须
    命中 `report:generate_assigned|report:generate_all` 及 property scope。P0 不提供报告共享、ACL
    管理、owner 转移或租客下载，因此不建立 `report_access_grants`。

### 6.8 账号删除与领域数据清理

1. Identity 先同时调用 Property Leasing 和 Maintenance 做初检；存在
   pending_signature/executed/active lease 时返回 `409 active_lease_blocks_deletion`，存在
   open/assigned/in_progress/blocked 工单时返回 `409 open_maintenance_orders_block_deletion`。用户必须
   先拒绝待签合同、完成租约终止/自然结束，并等待 Property Manager 完成或取消全部非终态工单；
   任一依赖不可确认时 fail-closed，禁止删除账号绕过租约或工单状态机。
2. `DELETE /api/v1/me/account` 创建持久 deletion request，立即撤销 session/token，并将账号置为
   `deletion_pending`；重复请求返回同一 request。所有新的客户写命令必须校验 Identity 状态并拒绝
   `deletion_pending`。
3. 账号冻结后 Identity 再次调用两项资格检查，收口初检与冻结之间已在途的写事务。若发现新
   blocker，deletion request 保持 `blocked` 并由 worker 定期重查；用户等待 Property Manager 或
   有权员工完成/取消相关业务。只有复检无 blocker 才发布删除事件，不引入跨服务锁或分布式事务。
4. Identity 通过 outbox 发布 `identity.subject_deletion_requested.v1`。Property Leasing、Maintenance
   和 Inspection Report 按 subject 删除该用户的申请、case、消息、合同/账单、工单，以及
   仅由该用户拥有的 tenant report、文件和 MinIO 对象，并通过 inbox 保证幂等。
5. 员工生成、属于 property 的报告不会因某个 tenant 删除账号而删除；报告本身不得复制租客姓名、
   邮箱等 PII。Property Leasing 删除 lease/subject 映射后，其 `source_lease_id` 只是不可回推主体的
   失效业务引用，不再授予任何客户访问。Tenant 自己创建的报告及文件随账号删除。
6. 各服务写 deletion acknowledgement；全部成功后 Identity 删除凭据和可识别资料并完成账号
   删除。部分失败保持 deletion_pending，由 worker 重试并告警，禁止恢复登录。
7. Identity 正式保留不可恢复个人身份的删除 Tombstone：
   `deletion_request_id,subject_fingerprint,fingerprint_version,status,completed_at`。其中
   `subject_fingerprint=HMAC(deletion_pepper,subject_id)`，使用独立受管密钥，业务 API 永不返回。
   Tombstone 用于删除幂等、拒绝迟到/重放事件重新创建用户关联和安全审计；不得包含 subject_id、
   email、姓名或其他可识别资料。异步消费者处理可能重新创建 subject 关联的迟到/重放事件前，
   必须先通过 Identity SubjectProjection 确认账号仍 active；账号不存在时再检查 Tombstone。
   `deletion_pending`、Tombstone 命中或 Identity 不可用均 fail-closed。
8. Tombstone 在系统生命周期内保留；密钥轮换必须保留可验证的 `fingerprint_version`，访问仅限删除
   worker/安全管理员并记录审计。它不恢复账号，也不允许重新关联被删除的数据。
9. “历史合同永久保留”指账号正常存续期间没有自动过期；用户主动删除账号是唯一产品例外。
   正式商用前必须经所在地合同、税务和隐私留存要求复核；如法规要求留存，改为不可逆匿名化而
   不是保留可识别账号。

## 7. 功能需求

| ID | 需求 | 优先级 | 数据所有者 |
|---|---|---|---|
| FR-IAM-01 | 双端统一登录并按 account_type 返回 Portal | P0 | Identity |
| FR-IAM-02 | Customer 自助注册固定成为 prospect | P0 | Identity |
| FR-IAM-03 | 幂等初始化 12 个 active staff 并按角色签发权限 | P0 | Identity |
| FR-IAM-04 | Manager Admin 查看员工账号、角色与 permission；Customer 跨服务删除 | P0 | Identity + domains |
| FR-PROP-01 | Guest/customer 浏览公开房源 | P0 | Property Leasing |
| FR-PROS-01 | Customer 联系真人业务员并查看本人会话 | P0 | Property Leasing |
| FR-APP-01 | Prospect/Former Tenant 创建和提交租房申请；Tenant 历史只读 | P0 | Property Leasing |
| FR-APP-02 | 业务员审核申请 | P0 | Property Leasing |
| FR-APP-03 | 任一租约执行后幂等收口该客户其他申请、case 和 draft lease | P0 | Property Leasing |
| FR-LEASE-01 | 业务员从批准申请创建合同 | P0 | Property Leasing |
| FR-LEASE-02 | 租客签署、公司签署、执行合同 | P0 | Property Leasing |
| FR-LEASE-03 | 租赁事件更新 customer status | P0 | Property Leasing + Identity |
| FR-LEASE-04 | 取消、待签过期、激活、自然结束和提前终止完整释放唯一当前租约 slot | P0 | Property Leasing |
| FR-LEASE-05 | 数据库拒绝同一 property 的重叠待签/执行/有效租期 | P0 | Property Leasing |
| FR-MNT-01 | Tenant 为本人租赁房源报修 | P0 | Maintenance |
| FR-MNT-02 | Manager 分派，Maintainer 推进工单 | P0 | Maintenance |
| FR-RPT-01 | Property Manager/Manager Admin，或 active Lease 的当前 Tenant，为 property 异步生成原有报告 | P0 | Inspection Report |
| FR-RPT-02 | 报告直接依附 property，并以 `source_lease_id`、本人 Lease 关系和状态隔离不同租期用户 | P0 | Inspection Report |
| FR-BFF-01 | 两个 Portal 提供稳定页面契约和脱敏投影 | P0 | Portal API |
| FR-BFF-02 | Manager Admin 查看全部租约/维修双方详情；P0 不含业绩和月销售 | P0 | Staff Portal |

## 8. 服务边界和调用归属

| 能力 | Portal/BFF | 最终业务服务 | 说明 |
|---|---|---|---|
| 注册、登录、refresh、员工种子 | Gateway 直达／启动任务 | Identity | 不在 Portal 保存会话真相 |
| 员工／客户首页 | 两个 Portal 聚合 | 多个服务 | BFF 只返回页面投影 |
| 房源、联系、申请、合同 | 对应 Portal | Property Leasing | 状态机和事务均在领域服务 |
| 客户身份阶段 | Portal 展示 | Identity 投影，来源为 Leasing 事件 | 前端/管理员不可直接修改 |
| 维修 | 对应 Portal | Maintenance | Leasing 只提供房源/租约授权投影 |
| 检查、视频、租期报告 | Staff/Tenant Portal | Inspection Report | Pipeline 继续复用旧实现 |
| 公共帮助内容 | Tenant Portal | Knowledge | 非本期主链路，可独立缓存 |

Portal 无业务数据库，只允许短期只读缓存。领域服务不接受浏览器伪造的
`X-Actor-Subject`，必须从已验证 token／委派 token 中得到 actor。

### 8.1 Docker 部署拓扑与端口

所有微服务、worker、双 React 前端、双 BFF、Redis、MinIO、PostgreSQL 和未来向量数据库均由
Docker Compose 管理。只有 Gateway 对浏览器公开；微服务端口仅在 Compose 网络内访问。

| 容器 | 内部端口 | 说明 |
|---|---:|---|
| `identity-access-service` | 8001 | Identity、session、RBAC、客户阶段 |
| `property-leasing-service` | 8002 | 房源、潜客、申请、合同、租约、账单 |
| `maintenance-service` | 8003 | 维修工单 |
| `inspection-report-service` | 8004 | 视频、job、property report、PDF、租期访问校验 |
| `knowledge-service` | 8005 | 公共/客户/员工知识投影 |
| `staff-portal-api` | 8006 | 员工 BFF |
| `tenant-portal-api` | 8007 | 租户/潜户 BFF |
| `staff-agent-service` | 8008 | 预留，非本期主链路 |
| `tenant-agent-service` | 8009 | 预留，非本期主链路 |
| `staff-web` / `tenant-web` | 各自 80 | React 静态服务，仅 Gateway 反代 |
| `report-worker` / outbox workers | 无业务端口 | 使用所属服务镜像运行后台任务 |
| PostgreSQL / Redis | 5432 / 6379 | 持久真相与缓存/流量治理 |
| MinIO | 9000 / 9001 | 对象 API/控制台 |
| Qdrant（未来） | 6333 / 6334 | HTTP/gRPC 向量检索 |

P0 默认 Compose profile 只启动 Gateway、两个 React、两个 BFF、Identity、Property Leasing、
Maintenance、Inspection Report API/Worker、PostgreSQL、Redis 和 MinIO。Knowledge/Qdrant 使用
`future` profile，两个 Agent 使用 `agent` profile；它们仍以 Docker 定义保留，但不得成为非 Agent
P0 健康检查或主链路的启动依赖。

Gateway 单入口采用同源路径分流：`/staff/* → staff-web`、`/tenant/* → tenant-web`、根路径跳转
`/tenant/`；`/api/v1/staff/* → staff-portal-api:8006`、`/api/v1/tenant/* →
tenant-portal-api:8007`，Identity 路径直达 8001。两套 React 分别配置 Vite base 和 Router
basename，浏览器无需直接访问内部容器或处理跨域 cookie。

### 8.2 MVP 必需 schema 增量

现有目标 schema 已经提供主要聚合，但要让本 PRD 真正可运行，还需要由各数据所有者新增以下
最小字段/表。它们是显式 migration，不是 Portal 临时 JSON 或跨 schema 表：

| 所有者 | 增量 | 原因 |
|---|---|---|
| Identity | 删除/不再写 `active_lease_count`；状态事件仅保存 `to_status + aggregate_version` | Identity 只做客户阶段投影，唯一当前租约由 Property Leasing 保证 |
| Property Leasing | application 增加 `desired_start_on,term_months,occupants,note,closed_reason,closed_at,winning_lease_id` 和 `ineligible/expired` 状态 | 支撑最小申请和租约执行后的自动收口与审计 |
| Property Leasing | lease 增加必填且唯一的 `application_id` FK | 保证一份 approved application 最多生成一份 lease，并可回溯承租人来源 |
| Property Leasing | `lease_documents` + lease `offer_expires_at` | 保存不可变合同版本、terms JSON/HTML、digest 和待签期限 |
| Property Leasing | building `timezone`（IANA） | 统一解释起租日、到期日和 lifecycle worker 边界 |
| Property Leasing | `lease_signature_events` | 保存逐签署人、签署侧、document ID、digest、IP/UA hash 与审计 |
| Property Leasing | 删除/不再创建 `lease_access_grants` | 访问直接使用 `subject → party → lease_tenants → lease`，避免重复授权状态 |
| Maintenance | order 增加 `lease_id,description` | 证明租客报修授权关系并保存基础详情 |
| Property Leasing | `customer_lease_slots` | 数据库唯一 subject 槽位，禁止并发创建第二份待签/有效租约 |
| Property Leasing | `btree_gist` property/date exclusion constraint | 禁止同一 property 的待签/已执行/有效租期重叠 |
| Inspection Report | report 增加必填 `property_id`、可选 `source_lease_id/legacy_context_id` | 业务归属从 chat 改为 property，旧 ID 仅用于迁移适配 |
| Inspection Report | 不创建 `report_access_grants` | P0 直接使用 source_lease_id + 承租关系/Lease 状态；共享/动态 ACL 不在范围 |
| Identity | `subject_deletion_requests/acknowledgements` + `subject_deletion_tombstones` | 持久化跨服务删除状态，并阻止迟到事件重新创建已删除主体关联 |

附件上传不是 P0 骨架的完成条件；上线 P1 图片附件时由 Maintenance 拥有附件元数据和私有对象
生命周期，不能借用 Report 的业务文件表或由 Portal 保存对象 key。

## 9. API 与事件总览

详细契约见 `docs/backend/api/`：

- `identity-access-api.md`
- `staff-portal-api.md`
- `tenant-portal-api.md`
- `property-leasing-api.md`
- `maintenance-api.md`
- `inspection-report-api.md`
- `knowledge-api.md`

P0 页面到接口的可追溯关系：

| 用户动作／页面 | 浏览器入口 | 领域接口所有者 |
|---|---|---|
| 双端注册／登录／会话 | Gateway → Identity `/api/v1/auth/*`、`/api/v1/me*` | Identity |
| 租户房源、联系和申请 | Tenant BFF `/properties`、`/contact`、`/applications` | Property Leasing |
| 员工房源和我的订单 | Staff BFF `/properties`、`/orders`、`/applications`、`/leases` | Property Leasing |
| 双方签署与执行合同 | Tenant/Staff BFF `/leases/*` | Property Leasing |
| 我的房子／合同／缴费 | Tenant BFF `/my-property`、`/leases/*` | Property Leasing 聚合来源 |
| 租客报修／员工处理 | Tenant/Staff BFF `/maintenance-orders/*` | Maintenance |
| 双端视频报告 | Tenant/Staff BFF `/reports/*` | Inspection Report + 原 Pipeline adapter |
| Topbar、菜单和首页卡片 | 两个 BFF `/bootstrap`、`/topbar`、`/home|dashboard` | BFF 聚合，不拥有领域数据 |

核心事件：

| 事件 | 生产者 | 消费者 | 用途 |
|---|---|---|---|
| `customer.tenancy_status_changed.v1` | Property Leasing | Identity | 执行时明确投影为 tenant，结束/终止时明确投影为 former_tenant；带 aggregate_version，不携带租约 count |
| `application.invalidated.v1` | Property Leasing | Staff Portal/通知投影 | 一份租约执行后关闭该客户其他申请 |
| `lease.executed.v1` | Property Leasing | Maintenance、Report、Portal | 开放当前租赁期能力和失效缓存 |
| `lease.cancelled.v1`/`lease.expired.v1` | Property Leasing | Portal | 释放待签 slot、刷新订单；不改变 customer status |
| `lease.ended.v1`/`lease.terminated.v1` | Property Leasing | Maintenance、Report、Portal | 关闭当前租赁能力并切换为历史只读入口 |
| `property.status_changed.v1` | Property Leasing | Portal 缓存失效 | 公开列表和员工投影失效 |
| `maintenance.order_changed.v1` | Maintenance | Portal 缓存失效/通知 | 刷新工单列表 |
| `report.completed.v1` | Inspection Report | Portal 缓存失效/通知 | 报告可审阅 |
| `identity.subject_deletion_requested.v1` | Identity | Leasing、Maintenance、Report | 幂等删除/匿名化 subject 相关领域数据并回执 |

事件使用本服务 outbox 与消费方 inbox，至少一次投递，按 `event_id` 幂等。

所有服务错误必须遵循 `docs/backend/api/README.md` 的统一结构、HTTP 映射和 P0 错误码注册表。
领域内部可保留诊断子码；BFF 面向浏览器必须把全部私有资源不存在/不可见错误统一为
`404 resource_not_found` 和空 details。其他错误保留下游 `code/status/retryable/details`，仅本地化
message；不得把同一业务冲突在不同 Portal 映射成不同错误码。

## 10. 缓存、高并发与可靠性

### 10.1 Redis 的职责

Redis 是加速和流量治理组件，不是业务真相。生产环境建议每个服务使用带服务前缀的逻辑
命名空间，禁止多个服务通过 Redis 共享可写领域对象。

| 场景 | 模式 | 建议 TTL／规则 |
|---|---|---|
| 公开房源列表/详情 | cache-aside | 30–120s，状态事件主动失效，TTL 加 10% jitter |
| Portal dashboard 聚合 | 每用户/权限版本缓存 | 10–30s；key 含 subject、role/status version、filter hash |
| JWKS／低风险权限模板 | 本地 L1 + Redis L2 | 5–15min；版本变化 pub/sub 失效 |
| Identity token introspection | 只缓存 active 短结果 | 不超过 access token 剩余 TTL，key 含 jti/aud |
| Gateway/API 限流 | Redis 原子计数或令牌桶 | 按 IP、账号、subject 和 route 组合 |
| 幂等响应 | Redis 可作快速层，DB 为权威 | 24h；写结果必须有数据库唯一约束／记录兜底 |
| 热点空结果 | 短负缓存 | 5–15s；仅公开/非敏感不存在结果 |
| 报告进度推送 | Redis Pub/Sub 可选 | 仅实时通知；持久事件仍在 PostgreSQL |

禁止缓存：密码结果、refresh token、合同签署结论、维修写入结果、资源级授权最终决定、
未脱敏租客资料和 MinIO presigned URL 的超期副本。合同执行、报告状态、RBAC 和支付类高风险
请求在缓存不可确认时必须失败关闭或回源，不能 fail-open。

### 10.2 防击穿、雪崩和脏数据

- 热点 key 使用 single-flight／短分布式锁，未获得锁的请求读取短期 stale 值或回退。
- TTL 增加随机抖动；批量失效后逐步预热公开房源。
- 缓存 key 必须包含 `schema_version` 和数据投影版本。
- 写成功后先提交数据库与 outbox，再删除缓存；消费者重复删除必须安全。
- Portal 不缓存下游 401/403。404 只有公开资源可以短暂负缓存。
- Redis 故障时普通查询回源并限流；安全判断和写命令不依赖 Redis 单点正确性。

### 10.3 数据库和 HTTP

- 大列表使用 cursor，不使用深 `OFFSET`；只查询投影所需列。
- 批量 subject/property 查询避免 N+1，内部 batch 上限 200。
- 每实例数据库连接池从 `pool_size=10,max_overflow=10` 压测起步，按数据库连接预算调整。
- Portal 下游连接池复用 keep-alive；普通查询连接超时 300ms、总超时 1.5s。
- GET 对 429/503/连接失败最多重试两次并使用指数退避；写命令只有携带幂等键才可重试。
- BFF 聚合设置总 deadline；非关键卡片可返回 `partial_errors[]`，合同/维修等核心详情失败则整体失败。
- 视频上传采用流式接收与磁盘 spool；Gateway、API、MinIO 同步限制大小和超时。
- 报告任务使用 PostgreSQL `FOR UPDATE SKIP LOCKED`、lease/heartbeat 和独立 worker，不以 Redis
  队列替换当前可靠任务真相。

### 10.4 容量基线

MVP 压测基线：1,000 并发连接、公开房源读取 300 RPS、登录 20 RPS、普通写入 50 RPS、
50 个并发上传连接；视频分析 worker 并发由 GPU/模型额度单独限制，默认 1，不计入普通 API
延迟 SLO。最终参数必须由预发布压测确定，而不是仅按文档默认值上线。

## 11. 安全与合规

- Access token 短期、audience 限定；refresh token 只进 Secure/HttpOnly/SameSite cookie 并轮换。
- Gateway 做第一层验签，领域服务继续做具体资源授权。
- Customer 访问 lease、maintenance、report 时均使用 `subject → party → lease_tenants → lease` 链路，并校验 Lease 状态和资源归属。
- Staff 授权为 active staff ∩ permission ∩ resource scope/assignment。
- 对无权访问或不存在的私有资源，领域内部可以保留诊断子码，但 HTTP 一律为 404；Portal 面向
  浏览器统一返回 `resource_not_found`。只有已经确认资源属于/可见于当前用户、但角色或客户阶段
  禁止动作时才返回 403。
- 所有外部 ID 使用 public UUID；不暴露 bigint、数据库键、对象 key 或内部 MinIO 地址。
- 合同签署、角色调整、工单改派、报告生成/删除写不可变审计。
- 日志不得记录密码、token、完整身份证件、原始视频内容或未脱敏联系信息。

## 12. 视频报告迁移约束

### 12.1 不可改动的旧业务内核

以下代码在迁移中视为受保护内核：

- `backend/app/workflow/orchestrator.py` 的流程语义；
- `backend/app/agents/*` 中用于视频报告的模型/提示词行为；
- 抽帧、筛选、YOLO、场景分析、评分、验证和最多三轮修复语义；
- `backend/app/pdf/*` 的 PDF 生成结果；
- 原 report JSON 字段和证据图片语义。

### 12.2 Strangler 迁移步骤

1. 对旧 `POST /api/uploadVideo`、`POST /api/processVideoStream`、job 查询、PDF 导出和下载建立
   回归契约快照。
2. 在 inspection-report-service 建立 adapter，先原进程内调用旧 Service/Workflow 接口；禁止
   复制一份 Pipeline。
3. 用 subject/public UUID 适配原整数 user ID；新 report 直接保存 `property_id`，为旧 Pipeline
   生成不对外暴露的 `legacy_context_id` 适配旧 chat ID。
4. 新入口采用 `202 + job_id`，旧 NDJSON 路径继续兼容前端直到新 Portal 切换完成。
5. 加入 inspection/property/`source_lease_id` 关联和外围授权检查；不进入 Pipeline state。
6. 前端切至 staff/tenant Portal 契约并通过双路径金丝雀回归。
7. 新路径连续通过功能、输出快照、故障恢复和性能验收后关闭旧 Gateway 路由。
8. 最后移动代码目录；同一时刻只能有一个路径写报告表，禁止双写。

回归判定：同一固定视频与 mock 模型输出下，报告 schema、关键字段、验证结论、证据顺序和
PDF 内容语义一致；允许 public ID、时间戳和持久化路径不同。

## 13. 交付计划

| 阶段 | 内容 | 完成条件 |
|---|---|---|
| M0 契约冻结 | PRD、API、事件、状态机、测试夹具 | 评审通过，无未决 P0 业务问题 |
| M1 身份接入 | 双端登录、12 人种子、Portal 跳转 | Identity 契约和 UI E2E 通过 |
| M2 房源与潜客 | 房源、联系、申请 | customer↔consultant 闭环通过 |
| M3 租约 | 审核、自动收口、签署、执行、取消/过期/自然结束、身份事件、重叠租期约束 | customer/lease 生命周期闭环 |
| M4 维修 | 租客报修、分派、处理 | 权限和状态机 E2E 通过 |
| M5 报告迁移 | 旧 Pipeline adapter、property/source lease 关联、租客访问 | 输出回归和恢复测试通过 |
| M6 性能与切换 | Redis、限流、压测、观测、旧路由下线 | SLO 达标且无双写 |

建议按 6 个双周迭代规划，并预留 20% 用于联调、数据修复和安全整改。日期由团队容量评审
后确定，本文不承诺未经估算的自然日。

## 14. 验收场景

### AC-01 双端身份

- 初始化后 12 个约定员工均可用各自邮箱和密码登录，数据库中不存在明文密码。
- Customer 注册后进入 tenant Portal，状态为 prospect。
- 同一登录接口不能由前端强制改变 portal/account_type。

### AC-02 房源到合同

- Guest 只能看到公开 marketing 房源，不能读取 private/staff 字段。
- Customer 联系业务员后，双方可在同一真人线程发送消息且重复消息不重复入库。
- Customer 提交申请，非负责业务员无法查看其联系方式或审核。
- 申请批准后创建合同；缺少任一必需签名不能执行。
- Tenant 不能创建新申请或签署第二份租约；并发待签请求只有一个能占用 lease slot。
- 一份租约执行后，其他申请/case/draft lease 按第 6.4 节自动收口，相关业务员页面可见。
- 除获胜 application 外，所有其他 approved application 均变为 expired；其已生成的非终态 draft
  lease 同时 cancelled，并记录 another_lease_executed、closed_at 和 winning_lease_id。
- 同一 property 的重叠待签/执行/有效租期被数据库约束拒绝。
- 合同执行后更新唯一 customer lease slot 并写 outbox，重复执行不产生第二份合同或事件。
- Identity 消费后 customer 变为 tenant；旧 prospect token 在敏感操作中失效或被拒绝。
- 待签取消/过期释放 slot 且不改变客户阶段；自然结束/提前终止后客户成为 former tenant。
- 主动撤回、拒签、员工取消或报价过期会按第 6.4–6.5 节同步关闭 application/case、取消 Lease、
  释放 slot 并恢复正确房源可租状态，不留下孤立草稿。

### AC-03 维修

- Prospect 即使知道 property ID 也不能创建租客维修工单。
- Tenant 只能为本人有效租约房源报修。
- `executed` 待入住阶段只能查看合同/房产；达到 starts_on 且 lease active 后才能报修和生成报告。
- Property manager 只能在 scope 内分派；Maintainer 只能更新自己的工单。
- 并发更新时只有正确 version 成功，失败方收到 409。

### AC-04 视频报告

- 上传超限、非视频、越权 property 均被拒绝且不留下可访问孤儿对象。
- API 或 SSE 中断后，worker 继续任务，页面能用 job ID 恢复进度。
- 同一 property/提交幂等键不重复生成 active job/report，重试不生成重复 report。
- 原 Pipeline 回归快照通过。
- Customer 侧只有 Tenant 可从“我的房子”为当前 property 发起生成并查看报告；Prospect 无报告能力。
- Former Tenant 只能从历史租约的房源详情查看该租期已有报告，不能创建、修改、分享、删除或下载。
- Property Manager/Manager Admin 仍可按 scope 生成；存在 active Lease 时自动绑定 source_lease_id，
  空置房源报告只对 staff 可见。
- 报告必须有 property_id；租客报告还必须匹配本人 source_lease_id；无权用户或未来租客读取返回 404。
- 租约结束后 Former Tenant 仍可从历史租约入口只读查看该 `source_lease_id` 的报告；不能下载、
  修改、分享、删除或新建报告。

### AC-05 账号删除

- 删除请求立即禁止继续登录，重复提交不创建第二个删除任务。
- 各领域删除处理可重试且幂等；未全部回执前 Identity 保持 deletion_pending。
- 用户专属合同、申请、工单、消息、tenant report 和对象存储文件按第 6.8 节清理。
- 员工生成的 property report 不被误删，但不再保留被删除用户的可识别关联。
- 存在非终态维修工单时删除返回 open_maintenance_orders_block_deletion；工单完成或取消后才可重试。
- 删除完成后保留无 subject/email 的 HMAC Tombstone；迟到或重放事件不得重新创建用户关联。

### AC-06 高并发与故障

- Redis 正常时命中率、延迟和限流指标可观测。
- Redis 不可用时公开读取可受控回源，合同执行和资源授权不会 fail-open。
- 下游非关键卡片超时可返回部分结果；核心合同详情不可返回伪成功。
- 压测达到第 10.4 节基线且错误率、数据库连接、锁等待和队列延迟不超阈值。

## 15. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| Portal 承载业务规则形成新单体 | 高 | 状态机、事务和授权最终判断固定在领域服务；消费者契约测试 |
| Identity 文档能力超出现有 runtime 加固 | 高 | 上线前完成 Origin 白名单、持久幂等、验证码/限流；固定员工 seed 严禁生产启用 |
| 合同确认被误认为合规电子签 | 高 | UI/条款明确 MVP 性质，商用前接第三方签章与法务评审 |
| Redis 缓存陈旧导致越权 | 高 | 授权 key 带版本、高风险回源、事件失效、禁止缓存最终资源授权 |
| 报告迁移改变输出 | 高 | 受保护内核、固定夹具快照、单写切换、快速回滚路由 |
| 跨服务事件延迟造成身份状态暂时不一致 | 中 | Property Leasing 的承租关系、Lease 状态和唯一 slot 为业务真相；消费者幂等、重试与积压告警 |
| 热门房源缓存击穿 | 中 | jitter、single-flight、预热和数据库索引 |

## 16. 上线门禁

- 所有 P0 接口有 OpenAPI、消费者契约、生产者验证与稳定错误码。
- 关键状态迁移有单元、数据库集成和 E2E 测试。
- 无跨 schema ORM、无 Portal 业务表、无领域服务共享 Redis 可写对象。
- Alembic 包含 report `property_id/source_lease_id` 等必要 schema delta，并有空库重建测试。
- 视频旧路径回归与新路径输出对比通过，且没有双写。
- 安全测试覆盖 IDOR、token audience、CSRF、refresh 重放、上传类型/大小和限流。
- Dashboard 展示 P95/P99、5xx、连接池、Redis 命中率、outbox 积压、job queue/lease 与越权拒绝。
- Runbook 包含 Redis/DB/MinIO/worker 故障和报告任务恢复步骤。

## 17. 原始任务追踪矩阵

| 任务 | 文档落点 | 完成判定 |
|---|---|---|
| 非 Agent 全业务骨架 | 第 4–7、14 节 | 双端身份→房源→联系→申请→签约→维修→报告 E2E |
| 复用现有 Identity | 第 6.1–6.2 节及 Identity API 第 14–16 节 | 真实接口、session/token 与 Portal 跳转一致 |
| 保留旧视频业务并迁移 | 第 6.7、12 节及 Inspection Report API | Pipeline 无复制/改义，新旧输出回归通过 |
| 明确微服务/BFF 边界 | 第 8 节与两份 Portal API | 每个业务事实只有一个 owner |
| 每个非 Agent 服务接口 | 第 9 节接口索引 | 7 份服务/BFF API 文档齐全 |
| Redis/高并发设计 | 第 10 节及各 API 的缓存章节 | 压测、降级、失效和不 fail-open 验收通过 |
