# 后端 API 契约规范

## 服务接口清单

- [Identity Access Service API](identity-access-api.md)
- [Staff Portal API](staff-portal-api.md)
- [Tenant Portal API](tenant-portal-api.md)
- [Property Leasing Service API](property-leasing-api.md)
- [Maintenance Service API](maintenance-api.md)
- [Inspection Report Service API](inspection-report-api.md)
- [Knowledge Service API](knowledge-api.md)

以上文档覆盖非 Agent MVP。`staff-agent-service` 与 `tenant-agent-service` 明确不在本期产品
链路和接口交付范围内。

## P0 契约冻结规则

- PRD 定义用户流程、角色能力和 P0/P1 范围；本 README 定义跨服务 HTTP/错误/幂等公共规则；各
  service API 文档定义资源、状态机和端点。出现冲突时先按此层级修正文档，不允许实现自行选择。
- 各 API 文档中未标为 P1、future 或 legacy compatibility 的端点均属于 P0；P1 端点不得阻塞 P0
  Compose readiness 或主链路 E2E。
- P0 只实现页面和主链路实际调用的端点，不预建通用工作流、动态 ACL、分布式事务或独立调度
  服务。数据库约束负责最终一致性，Redis 只负责缓存、限流和通知。
- 开始业务代码前冻结本文档集合；实现阶段由每个 HTTP 服务导出与冻结文档一致的 OpenAPI，并以
  Portal 消费者契约和领域生产者测试阻止漂移。OpenAPI 是实现产物，不反向改变已确认业务规则。

## Docker 服务端口

| 服务 | 内部端口 |
|---|---:|
| identity-access-service | 8001 |
| property-leasing-service | 8002 |
| maintenance-service | 8003 |
| inspection-report-service | 8004 |
| knowledge-service | 8005 |
| staff-portal-api | 8006 |
| tenant-portal-api | 8007 |
| staff-agent-service（预留） | 8008 |
| tenant-agent-service（预留） | 8009 |

浏览器只访问 Gateway；`/staff/*` 和 `/tenant/*` 分别返回两个 React 应用，API 分别进入两个
Portal BFF。Worker 不占用上述业务 HTTP 端口。

P0 默认 Compose 不依赖 Agent、Knowledge 或向量检索：Knowledge/Qdrant 放入 `future` profile，
两个 Agent 放入 `agent` profile。它们仍有 Docker 定义和预留端口，但关闭时不得影响 P0 readiness。

## 路径与版本

- 外部 HTTP 统一经 Nginx `/api`，服务 API 使用 `/api/v1/<resources>`。
- 健康检查不鉴权：`/health/live` 只检查进程，`/health/ready` 检查必要依赖。
- 资源使用复数名词和稳定 public ID；动作仅用于无法表达为资源状态变化的操作。
- 内部接口使用 `/internal/v1`，网关不得向公网暴露。

## 请求上下文

服务间统一传播：

- `Authorization: Bearer <token>`：用户或服务身份；
- `X-Request-ID`：入口请求 ID，不存在时由入口生成；
- `traceparent`：分布式追踪；
- `Idempotency-Key`：可重试写操作；
- `X-Actor-Subject`：仅由受信服务根据已验证 token 生成，禁止信任公网直传值。

创建新的 customer 关联数据时，入口 BFF 必须成功交换当前有效 token；由 staff 发起但会为某
customer 新建待签合同等关系的命令，领域服务还必须读取 Identity 最小 SubjectProjection，拒绝
`deletion_pending/deleted`。这样不需要把客户状态复制到各领域数据库。

## 成功与错误

成功响应直接返回资源或分页结果。所有服务和 BFF 使用同一错误结构：

```json
{
  "error": {
    "code": "lease_state_conflict",
    "message": "租约当前状态不允许此操作",
    "request_id": "019...",
    "retryable": false,
    "details": {}
  }
}
```

- `code` 是跨服务稳定机器键；`message` 可本地化；`details` 不包含密钥、SQL 或内部堆栈。
- `retryable` 只能由服务端判定；客户端不得仅凭 HTTP status 猜测写命令是否可重试。
- Service 抛领域异常，统一异常处理器负责映射 HTTP；Mapper 异常不得原样返回。

### P0 统一错误码注册表

| HTTP | Code | 使用条件 |
|---:|---|---|
| 400 | `invalid_request` | JSON/请求协议无法解析，不用于字段业务校验 |
| 401 | `authentication_required` | 缺少凭据 |
| 401 | `invalid_token` / `token_expired` / `token_stale` | token 无效、过期或授权版本落后 |
| 403 | `csrf_invalid` | Cookie 写接口的 Origin/CSRF token 校验失败 |
| 403 | `action_forbidden` | 已确认资源可见，但角色或客户阶段禁止该动作 |
| 404 | `resource_not_found` | 公共资源不存在，或私有资源不存在/不可见；防止 IDOR 枚举 |
| 405 | `method_not_allowed` | 路径存在但 HTTP method 不支持 |
| 409 | `version_conflict` | 乐观锁版本不匹配；details 可返回安全的 current_version |
| 409 | `idempotency_conflict` | 同一主体/操作/幂等键对应不同请求摘要 |
| 409 | `state_conflict` | 当前领域状态不允许迁移；领域服务可使用下表的具体子码 |
| 413 | `payload_too_large` | 请求或上传超过统一配置上限 |
| 415 | `unsupported_media_type` | Content-Type/文件类型不支持 |
| 422 | `validation_failed` | 字段校验失败；details 仅返回字段与安全原因 |
| 423 | `account_temporarily_locked` | 登录失败达到阈值；设置安全的 Retry-After，不泄漏账号细节 |
| 429 | `rate_limited` | 共享限流触发；设置 Retry-After，`retryable=true` |
| 500 | `internal_error` | 未预期异常；不返回内部原因 |
| 502 | `dependency_invalid_response` | 下游返回不可解析或违反契约的响应 |
| 503 | `dependency_unavailable` | 必要下游/DB/对象存储不可确认，默认 fail-closed |
| 504 | `dependency_timeout` | BFF 或服务等待必要下游超时 |

P0 领域子码：

| 领域 | 稳定子码 |
|---|---|
| Identity | `invalid_credentials`, `account_temporarily_locked`, `invalid_refresh_token`, `refresh_token_expired`, `refresh_token_reused`, `account_unavailable`, `staff_account_unavailable`, `email_already_exists`, `action_token_invalid`, `session_inactive`, `customer_status_transition_invalid`, `account_deletion_pending`, `active_lease_blocks_deletion`, `open_maintenance_orders_block_deletion`, `subject_already_deleted` |
| Property Leasing | `property_not_visible`, `prospect_case_not_found`, `case_access_denied`, `customer_not_eligible_for_lease`, `customer_already_has_lease`, `application_state_conflict`, `application_superseded`, `application_already_has_lease`, `property_no_longer_available`, `lease_state_conflict`, `lease_offer_expired`, `lease_signature_incomplete`, `lease_terms_changed`, `lease_date_overlap`, `lease_slot_mismatch`, `lease_activation_not_due`, `lease_end_not_due`, `lease_access_required` |
| Maintenance | `lease_access_required`, `property_access_denied`, `order_not_found`, `order_state_conflict`, `assignee_inactive`, `assignee_not_allowed`, `attachment_unavailable`, `open_maintenance_orders_block_deletion` |
| Inspection Report | `inspection_not_found`, `property_access_denied`, `report_generation_not_allowed`, `current_lease_required`, `active_job_exists`, `job_not_found`, `file_not_ready`, `file_quarantined`, `report_not_found`, `report_access_denied`, `report_history_access_required`, `lease_report_mismatch`, `report_generation_failed`, `report_validation_failed` |
| Knowledge | `knowledge_base_not_found`, `knowledge_access_denied`, `document_version_conflict`, `index_job_failed`, `query_too_large` |

领域服务内部的 `*_not_found`、私有对象 `*_access_denied`、`*_access_required` 和
`property_not_visible` 全部映射 HTTP 404；
`customer_not_eligible_for_lease`/`report_generation_not_allowed` 等明确动作禁止映射 403；状态、
版本、重复占用、过期和条款冲突映射 409；处理失败按是否为未预期错误或依赖故障映射 500/503。
`active_lease_blocks_deletion`、`open_maintenance_orders_block_deletion` 和
`subject_already_deleted` 固定映射 409。
领域子码不得改变对应 HTTP 语义。错误采用两层对外、三层内部处理：

1. 领域服务内部日志/审计保留准确原因和领域子码，例如 `report_access_denied`；不得返回 SQL、堆栈或敏感 ID。
2. 领域服务的受信 `/internal/v1` 响应可以返回稳定领域子码，但所有“资源不存在或对 actor 不可见”均使用 HTTP 404 且 details 为空。
3. Portal BFF 面向浏览器时，必须把上述所有私有资源 404 归一化为同一
   `404 resource_not_found`，不得把 `*_not_found`、`*_access_denied`、`*_access_required`、
   `property_not_visible` 或 `report_history_access_required` 暴露给浏览器。服务端日志用 request ID
   关联原始内部子码。

除私有资源 404 归一化外，BFF 保留下游 HTTP status、稳定业务 code、`retryable` 和安全 details，
只本地化 message。多个非关键依赖失败时，`partial_errors[]` 中的每一项使用同一字段；其中私有
资源失败同样只能暴露 `resource_not_found`。

### P0 领域内部子码规范映射

未在下表声明为 `true` 的错误，`retryable` 一律为 `false`。客户端不得自动重放签署、执行、审批、
删除等写命令；即使收到可重试错误，也必须同时具备相同 `Idempotency-Key` 才能重试。

| HTTP | Code | 安全 details / 说明 |
|---:|---|---|
| 401 | `invalid_credentials` | 始终使用统一 message；不返回邮箱是否存在 |
| 423 | `account_temporarily_locked` | `retry_after_seconds`、可选 `locked_until`；禁止自动重试密码 |
| 401 | `invalid_refresh_token` / `refresh_token_expired` / `refresh_token_reused` | details 为空；reused 时撤销整个 token family |
| 403 | `account_unavailable` / `staff_account_unavailable` | 不返回内部停用原因；管理员投影另行审计 |
| 409 | `email_already_exists` | 仅注册提交者可见；不用于登录枚举 |
| 409 | `action_token_invalid` / `session_inactive` | details 为空 |
| 409 | `customer_status_transition_invalid` / `account_deletion_pending` | 可返回安全的 `current_status` |
| 409 | `active_lease_blocks_deletion` | `blocker_count`；仅本人可返回其 `lease_ids[]` |
| 409 | `open_maintenance_orders_block_deletion` | `blocker_count`；仅本人可返回其 `order_ids[]` |
| 409 | `subject_already_deleted` | 仅受信内部调用；不得返回 fingerprint |
| 404 | `property_not_visible` / `prospect_case_not_found` / `case_access_denied` / `lease_access_required` | 仅内部稳定子码；Portal 对浏览器统一为 `resource_not_found` |
| 403 | `customer_not_eligible_for_lease` | 可返回 `customer_status` 和允许阶段，不返回其他租约信息 |
| 409 | `customer_already_has_lease` | 本人/有权员工可返回 `conflicting_lease_id`、`current_state` |
| 409 | `application_state_conflict` | `current_state,allowed_states[]` |
| 409 | `application_superseded` | 本人/有权员工可返回 `closed_reason,winning_lease_id` |
| 409 | `application_already_has_lease` | 本人/有权员工可返回既有 `lease_id` |
| 409 | `property_no_longer_available` | 可返回 `availability`；不返回其他申请人/租客 |
| 409 | `lease_state_conflict` | `current_state,allowed_states[]` |
| 409 | `lease_offer_expired` | `offer_expires_at` |
| 409 | `lease_signature_incomplete` | `missing_sides[]`，不返回其他签署人的私密信息 |
| 409 | `lease_terms_changed` | `current_document_id,current_terms_digest` |
| 409 | `lease_date_overlap` | `requested_starts_on,requested_ends_on`；不返回冲突租客 |
| 409 | `lease_slot_mismatch` | details 为空；记录内部审计 |
| 409 | `lease_activation_not_due` / `lease_end_not_due` | `effective_on,building_timezone` |
| 404 | `order_not_found` / `property_access_denied` | 仅内部稳定子码；Portal 对浏览器统一为 `resource_not_found` |
| 409 | `order_state_conflict` | `current_state,allowed_states[]` |
| 409 | `assignee_inactive` | 可返回 `assignee_id`，不返回雇佣详情 |
| 422 | `assignee_not_allowed` | `field=assigned_staff_id,reason` |
| 409 | `attachment_unavailable` | `attachment_status`，不返回 object key |
| 403 | `report_generation_not_allowed` / `current_lease_required` | `required_lease_status=active`；不返回其他租约 |
| 404 | `inspection_not_found` / `job_not_found` / `report_not_found` / `report_access_denied` / `report_history_access_required` | 仅内部稳定子码；Portal 对浏览器统一为 `resource_not_found` |
| 409 | `active_job_exists` | 本人/有权员工可返回 `job_id` |
| 409 | `file_not_ready` / `file_quarantined` | `file_status`，不返回存储地址 |
| 422 | `lease_report_mismatch` | details 为空，服务端记录关联 ID |
| 500 | `report_generation_failed` / `report_validation_failed` / `index_job_failed` | 返回安全 `failure_category`；不得返回 provider 原文 |
| 404 | `knowledge_base_not_found` / `knowledge_access_denied` | 仅内部稳定子码；Portal 对浏览器统一为 `resource_not_found` |
| 409 | `document_version_conflict` | `current_version` |
| 413 | `query_too_large` | `max_chars` |

### Common details 白名单

| Code | details |
|---|---|
| `validation_failed` | `fields:[{field,reason}]`；reason 使用稳定枚举，不回显敏感原值 |
| `version_conflict` | `current_version`，仅资源本来对 actor 可见时返回 |
| `idempotency_conflict` | `operation`；不返回原请求摘要 |
| `rate_limited` | `retry_after_seconds`；同时设置 `Retry-After`，`retryable=true` |
| `dependency_unavailable` | `dependency` 使用公开服务代号，`retryable=true` |
| `dependency_timeout` | `dependency`、可选 `timeout_ms`，`retryable=true` |
| `dependency_invalid_response` | `dependency`，不得包含下游 body，`retryable=false` |

数据库/框架异常必须在服务边界转换：唯一约束、FK、CHECK、EXCLUDE、锁超时、连接异常和 Python/ORM
异常都不得直接成为 `error.code`。其中 `leases.application_id` 唯一冲突固定映射
`application_already_has_lease`，customer slot 唯一冲突固定映射 `customer_already_has_lease`，
property/date EXCLUDE 固定映射 `lease_date_overlap`。

## 分页、并发和幂等

- 大列表使用不透明 cursor，默认按 `(created_at, id)` 或业务排序键稳定排序。
- 可更新聚合返回 `version`/ETag，写入使用期望版本避免静默覆盖。
- 相同幂等键、主体和操作在有效期内必须返回同一业务结果；参数变化返回 409。
- 客户端只能重试明确标记可重试的超时、429 和 503，采用指数退避和抖动。

## 契约管理

- 每个 HTTP 服务导出 OpenAPI；每个事件有独立 JSON Schema/Pydantic schema 和版本。
- 生产者兼容旧消费者：新增字段默认可选，删除/改义必须升版本。
- Portal API 做消费者契约测试；领域服务做生产者验证。
- 日志记录 request ID、actor、service、operation、status 和 latency，不记录 token 或原始密码。
