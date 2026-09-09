# Staff Portal API（BFF）

> 状态：目标契约；待实现
> 用户：staff 账号
> 数据所有权：无业务表
> 容器监听端口：`8006`；对应 React：`staff-web:80`，Gateway 页面前缀 `/staff/`

## 1. 定位

Staff Portal API 是员工 React 页面与领域服务之间的后端适配层。它校验 audience、传播 actor
上下文、并行聚合 Identity、Property Leasing、Maintenance 和 Inspection Report，输出员工页面
稳定投影。它不实现租约/工单状态机，不直连领域数据库，不经过 Staff Agent。

外部前缀统一 `/api/v1/staff`。登录、refresh、logout 和 `/me` 由 Gateway 直接路由到 Identity，
不在 BFF 复制实现。

员工 React 固定包含 Topbar 和侧边栏；侧边栏一级菜单为“房源信息、我的订单、维修工单、
Agent”。潜客、申请、待签约和历史成功合同 API 统一在“我的订单”页面组合展示。

## 2. 通用行为

- 只接受 `account_type=staff` 且 audience 匹配的 access token。
- 下游调用通过 Identity token exchange 获得 audience 限定的短期委派 token。
- 所有请求生成/传播 `X-Request-ID` 和 `traceparent`；写命令原样传播 `Idempotency-Key`。
- 资源访问的最终判定在领域服务。BFF 可做粗粒度菜单控制，但不能把它当授权证明。
- 聚合响应使用 `data`；非关键卡片失败时可附 `meta.partial_errors[]`。
- 合同、工单、报告详情等核心请求任何必要下游失败时整体返回稳定错误，不返回伪成功。

P0 页面/动作矩阵：

| 能力 | Leasing Consultant | Property Manager | Maintainer | Manager Admin |
|---|---:|---:|---:|---:|
| 房源信息 | 所有公开/空置详情，按大楼 | 负责楼栋全部房间和租赁摘要 | 仅工单 work context | 全部楼栋管理投影 |
| 我的订单 | 分配案件、申请、待签和历史成功合同 | — | — | 全部租约及双方详细信息 |
| 维修工单 | — | scope 内分派/查看/处理 | 本人被分派工单 | 全部工单及双方详细信息 |
| 员工账号与权限 | — | — | — | P0 查看；增删改和 scope 变更为 P1 |
| 生成视频报告 | — | scope 内 property | — | 任意 property |
| Agent 入口 | ✓ | ✓ | ✓ | ✓ |

矩阵决定菜单和 BFF 粗粒度拒绝；最终授权仍以 Identity permission 与领域 scope 的交集为准。

## 3. 页面 API

### 3.1 Bootstrap 与工作台

| 方法与路径 | 下游 | 返回／权限 |
|---|---|---|
| `GET /api/v1/staff/bootstrap` | Identity `/me`, `/permissions` | 当前员工、角色、scopes、菜单 feature flags |
| `GET /api/v1/staff/dashboard` | Leasing + Maintenance + Report | 按角色裁剪 assigned/all properties、prospect queue、work orders、report jobs 摘要；P0 不含业绩/月销售 |
| `GET /api/v1/staff/topbar` | Identity | display name、role、session/profile 菜单；不得返回密码或 token |

Dashboard 示例：

```json
{
  "data": {
    "staff": {"id": "staff-uuid", "display_name": "Alex", "role": "property_manager"},
    "cards": {
      "assigned_properties": {"count": 12},
      "open_prospects": {"count": 4},
      "open_maintenance": {"count": 7},
      "running_report_jobs": {"count": 1}
    }
  },
  "meta": {"partial_errors": []}
}
```

### 3.2 房源

| 方法与路径 | BFF 行为 |
|---|---|
| `GET /api/v1/staff/properties` | 转发过滤/cursor，返回当前员工可见投影 |
| `GET /api/v1/staff/properties/{id}` | 聚合房源、当前租约摘要、open 工单、最近检查/报告 |
| `POST /api/v1/staff/properties` | P1；转发 Leasing 创建命令 |
| `PATCH /api/v1/staff/properties/{id}` | P1；传播 version/幂等键 |
| `POST /api/v1/staff/properties/{id}/publish` | P1；转发发布命令 |

详情聚合不得向 leasing consultant 泄漏在租租客、租金履约、维修或内部报告数据。

角色投影：Leasing Consultant 按大楼查看所有公开/空置房源详细信息；Property Manager 只查看
管理 scope 内全部房间、占用状态、当前租客最小资料、合同/缴费和维修摘要；Manager Admin 可按
任意大楼查看管理投影；Maintainer 只通过工单 work context 获取必要房源信息。

### 3.3 我的订单：潜客联系人

| 方法与路径 | BFF 行为 |
|---|---|
| `GET /api/v1/staff/orders` | 页面级聚合；Leasing Consultant 按 assignment，Manager Admin 全局；按 `stage=contact|application|pending_signature|executed|ended`、building、assignee、cursor 查询摘要 |
| `GET /api/v1/staff/prospects` | 分配给本人/团队的 case 工作队列 |
| `GET /api/v1/staff/prospects/{id}` | case、property、application 和联系线程摘要 |
| `PATCH /api/v1/staff/prospects/{id}` | 推进 stage/status |
| `POST /api/v1/staff/prospects/{id}/assign` | Admin/team manager 改派 |
| `GET /api/v1/staff/contact-threads/{id}/messages` | 返回有权线程消息 |
| `POST /api/v1/staff/contact-threads/{id}/messages` | 传播 `client_message_id` 防重 |

### 3.4 我的订单：申请

| 方法与路径 | BFF 行为 |
|---|---|
| `GET /api/v1/staff/applications` | 分配 scope 内申请列表 |
| `GET /api/v1/staff/applications/{id}` | 聚合申请、case、房源与申请人最小身份 |
| `POST /api/v1/staff/applications/{id}/start-review` | 转发状态命令 |
| `POST /api/v1/staff/applications/{id}/approve` | 传播 version/幂等键 |
| `POST /api/v1/staff/applications/{id}/reject` | 传播 reason/version/幂等键 |

### 3.5 我的订单：待签和历史合同

| 方法与路径 | BFF 行为 |
|---|---|
| `GET /api/v1/staff/leases` | Leasing Consultant 按 assignment/scope；Manager Admin 返回全局列表 |
| `GET /api/v1/staff/leases/{id}` | LeaseView + property + 双方详细信息 + signing/lifecycle progress；Manager Admin 全局 |
| `POST /api/v1/staff/leases` | 从 approved application 准备合同 |
| `PATCH /api/v1/staff/leases/{id}` | 仅 draft 条款 |
| `POST /api/v1/staff/leases/{id}/send-for-signature` | 转发命令 |
| `POST /api/v1/staff/leases/{id}/company-signature` | 公司侧确认；高风险审计 |
| `POST /api/v1/staff/leases/{id}/execute` | 双方签完后显式执行 |
| `POST /api/v1/staff/leases/{id}/cancel` | draft/pending_signature 取消；reason/version/幂等键 |
| `POST /api/v1/staff/leases/{id}/terminate` | Manager Admin 或领域高风险权限；提前终止并审计 |
| `POST /api/v1/staff/leases/{id}/end` | Manager Admin 补偿自然结束；正常情况由 lifecycle worker 执行 |

BFF 不生成 `signed_at/executed_at`，不缓存签署或执行成功结果。下游 409 保留稳定错误 code。
`/orders` 只做分页摘要聚合，任何推进、审批、签署和执行仍调用对应领域命令，不能通过一个
“万能订单更新”接口绕过状态机。

Manager Admin 的 `AdminLeaseView` 固定由以下投影组成：

- lease：public ID/reference/status/version、starts_on/ends_on、weekly_rent/currency、
  offer/executed/ended 时间；
- property：public ID、building、房间号/公开地址和占用状态；
- customer side：customer public subject ID、display name、email、phone、application/case public ID；
- staff side：负责 Leasing Consultant/company signer 的 staff public ID、display name、role；
- contract：当前 document public ID/version/digest、双方签署状态与时间；
- billing：invoice count、open/overdue/paid amount 和最近缴费时间，不返回支付凭据；
- audit summary：最近状态变化、actor public ID、occurred_at、安全 reason code。

不得包含 password/token/session、完整 IP/UA、内部数据库 ID、对象 key、支付凭据或未脱敏内部异常。

### 3.6 维修

| 方法与路径 | BFF 行为 |
|---|---|
| `GET /api/v1/staff/maintenance-orders` | Property Manager scope、Maintainer assignment 或 Manager Admin 全局队列 |
| `GET /api/v1/staff/maintenance-orders/{id}` | Property Manager/Maintainer 最小必要投影；Manager Admin 返回租客与员工双方详细信息、property 和 timeline |
| `POST /api/v1/staff/maintenance-orders` | P1；staff 代建正式工单 |
| `POST /api/v1/staff/maintenance-orders/{id}/assign` | manager 分派/改派 |
| `POST /api/v1/staff/maintenance-orders/{id}/transitions` | maintainer/manager 状态迁移 |
| `POST /api/v1/staff/maintenance-orders/{id}/comments` | 工作记录/公开回复 |

Manager Admin 的 `AdminMaintenanceOrderView` 固定包含 order public ID/reference/status/priority/version、
summary/description、property/building、关联 lease public ID、报告租客的 public subject ID/display
name/email/phone、当前及历史分派员工的 staff public ID/display name/role、public/internal 标记后的完整
事件时间线和安全审计字段。它不得包含密码/token、完整 IP/UA、MinIO object key、支付凭据或其他
租客数据；Property Manager 和 Maintainer 仍使用各自最小投影，不能复用 Admin DTO。

### 3.7 Property 视频报告

| 方法与路径 | BFF 行为 |
|---|---|
| `GET /api/v1/staff/properties/{property_id}/reports` | 当前 staff 可见的 property 报告列表 |
| `POST /api/v1/staff/properties/{property_id}/reports` | 创建 property report；仅 Property Manager/Manager Admin |
| `POST /api/v1/staff/reports/{report_id}/files/videos` | raw video 流式代理到 Report Service |
| `POST /api/v1/staff/reports/{report_id}/jobs` | 创建持久任务，返回 202/job ID |
| `GET /api/v1/staff/report-jobs/{id}` | 查询状态与安全事件 |
| `GET /api/v1/staff/report-jobs/{id}/events` | SSE/NDJSON 透传，支持 after_sequence |
| `GET /api/v1/staff/reports` | scope 内报告列表 |
| `GET /api/v1/staff/reports/{id}` | 完整 staff 投影 |
| `POST /api/v1/staff/reports/{id}/exports/pdf` | P1；创建/复用 PDF 导出 |
| `GET /api/v1/staff/reports/{id}/download` | P1；授权后流式下载 |

BFF 对上传只做协议、速率和最大 body 初筛；文件状态和内容校验由 Report Service 最终负责。
创建时 Property Manager 必须同时拥有 `report:generate_assigned` 和 property/building scope；
Manager Admin 使用 `report:generate_all`。Leasing Consultant/Maintainer 即使伪造菜单请求也返回
403，领域服务再次执行相同授权。若 property 存在唯一 active Lease，服务端自动绑定
`source_lease_id` 并允许该租期 Tenant 查看；无 active Lease 时生成 staff-only 报告。P0 不提供
报告共享/ACL 管理接口。对外结构不返回旧 chat_id/legacy_context_id。

### 3.8 Identity 管理页面

| 方法与路径 | 行为 |
|---|---|
| `GET /api/v1/staff/admin/staff` | Manager Admin 聚合 Identity 员工账号、状态、角色和 permission 摘要；P0 只读 |
| `GET /api/v1/staff/admin/staff/{id}` | Manager Admin 查看单个员工账号、employment、角色、permission 和 role history；P0 只读 |
| `/api/v1/iam/*` | Gateway 直达 Identity；复用现有 51 operations 和 3 个删除编排/Tombstone 目标接口，不复制 IAM 写模型 |

Manager Admin 的 P0 管理页提供员工账号与权限查看。员工增删改、邮件激活、scope 变更、业绩和
月销售页面属于 P1；12 个员工仍由 Identity seed 初始化。IAM 写 API 继续作为后台兼容/未来管理
能力存在。

### 3.9 Agent 入口

`/staff/agent` 对所有 active staff 展示，要求 `agent:staff:use`。Agent 服务不参与本 PRD 的
确定性业务主链路；BFF 只提供导航/bootstrap，不复制 Agent 会话或编排接口。

## 4. 错误映射

BFF 遵循 [统一错误契约](README.md)。对于私有资源不存在、越权或不可见，领域服务内部虽然可以
返回不同诊断子码，但 BFF 面向浏览器一律返回 `404 resource_not_found`、空 details；原始子码仅随
request ID 写服务端日志。其他错误保留领域服务 `error.code`、`retryable` 和 HTTP status，只替换
用户可见本地化 message。下游连接
失败映射 `503 dependency_unavailable`，超时映射 `504 dependency_timeout`，并在 details 中仅
返回安全的 `dependency`；`retryable` 只使用错误对象的顶层字段。

审批、合同和报告主要透传：`application_state_conflict`、`application_superseded`、
`application_already_has_lease`、`customer_already_has_lease`、`property_no_longer_available`、
`lease_state_conflict`、`lease_signature_incomplete`、`lease_terms_changed`、`lease_date_overlap`、
`lease_slot_mismatch`、`lease_activation_not_due`、`lease_end_not_due`、`order_state_conflict`、
`assignee_inactive`、`assignee_not_allowed`、`report_generation_not_allowed`、`active_job_exists`、
`report_generation_failed` 和统一 version/idempotency 错误。除规定的私有资源 404 归一化外，BFF
不根据 message 猜测或改写 code。

聚合部分失败示例：

```json
{
  "data": {"property": {}, "open_orders": []},
  "meta": {
    "partial_errors": [{"component": "recent_reports", "code": "dependency_timeout", "retryable": true, "details": {"dependency": "inspection-report"}}]
  }
}
```

## 5. 缓存和流量治理

- `staff:bootstrap:{subject}:{auth_version}:{role_version}`：≤30s。
- Dashboard：10–20s；key 含 staff/role/scope version；允许 stale-while-revalidate ≤30s。
- 房源详情聚合：10–30s；不同 role/projection 使用独立 key。
- 不缓存 401/403、合同签署/执行结果、维修写命令、报告访问判定和运行中 job 终态判断。
- 写成功后根据 outbox 事件删除相关 dashboard/detail/list key；TTL 是最后兜底。
- 使用 Redis 分布式 rate limit，不使用进程内计数；上传、登录和普通 API 使用不同 bucket。
- P0 下游请求使用共享连接池、固定并发上限和明确 deadline；自动 circuit breaker/复杂 bulkhead
  策略属于压测证明需要后再增加的 P1 优化。
- BFF 总 deadline 建议 1.8s，单下游查询 1.2s；不得无限重试放大流量。

## 6. 契约测试

1. 登录 staff/customer token 只能进入对应 Portal audience。
2. BFF 菜单隐藏不能替代领域服务授权；伪造 public ID 仍被拒绝。
3. leasing consultant、property manager、maintainer 的详情字段投影严格不同。
4. 对 staff 无权访问的私有资源，随机不存在 ID 与真实越权 ID 的浏览器响应均为相同
   `404 resource_not_found`、空 details；内部诊断子码只存在服务端日志。
5. 幂等键、request ID、traceparent 和 actor context 正确传播。
6. 聚合超时只在声明为非关键的卡片产生 partial response。
7. Redis 不可用时读请求受控降级，写与授权不 fail-open。
8. 视频 body 流式代理，无整文件内存缓冲。
9. 只有 Property Manager/Manager Admin 能创建报告，且新报告必须绑定请求路径中的 property。
10. Manager Admin 可查看全部租约和维修工单双方详情及员工 permission；其他角色不能借此投影越权。
11. cancel/end/terminate 保留领域错误码；BFF 不自行释放 slot、修改 customer status 或伪造生命周期。
