# Identity Access Service API 契约清单

- 状态：P0 的 54 个 operations 已实现；账号跨服务删除与 Tombstone 闭环已纳入运行时验收
- 版本：v1
- 外部前缀：`/api/v1`
- 服务内部前缀：`/internal/v1`
- 容器监听端口：`8001`（仅 Compose 内网，不发布宿主机端口）
- 数据所有者：`identity-access-service`

本文是第一轮 Identity Service 代码迁移的接口契约。它从 `identity_access` schema、员工
RBAC、客户状态和双端登录流程反推，现由独立的
`backend/services/identity-access-service` 实现；旧 `backend/app/api/auth.py` 仅作为迁移期
兼容入口，不代表新服务的代码边界。

## 1. 核心产品决策

1. 员工端和客户端共用 `POST /api/v1/auth/login`，服务根据唯一账号的 `account_type`
   返回 `portal=staff|tenant`；前端不能提交或切换身份。
2. 公共注册只能创建 `customer + prospect`。员工不能自助注册；P0 由开发/演示环境的幂等
   seed 创建 12 个 active staff，不经过邮件激活。
3. access token 是短期、audience 限定 token，通过响应体返回并只保存在浏览器内存。
4. refresh token 是 opaque 随机值，只放在 `Secure + HttpOnly + SameSite` cookie；数据库
   只保存哈希，每次 refresh 都 rotation。
5. Customer 状态只有 `prospect/tenant/former_tenant`；只有 prospect/former tenant 可申请签约，
   租约执行后才是 tenant，且同一客户同时只能有一个租约。
6. token 中的 role/customer_status 是权限上限；具体房源、租约、工单和报告仍由对应领域
   服务做资源授权。
7. 所有对外 ID 都是 public UUID；任何接口都不返回 bigint 主键、密码哈希或 refresh token
   哈希。

## 2. 公共数据结构

### 2.1 UserView

```json
{
  "id": "user-public-uuid",
  "email": "user@example.com",
  "username": "Jeremy",
  "avatar": "https://gateway/.../avatar",
  "locale": "zh-CN",
  "account_type": "staff",
  "status": "active",
  "email_verified": true,
  "portal": "staff",
  "staff": {
    "id": "staff-public-uuid",
    "staff_code": "S0001",
    "display_name": "Jeremy",
    "employment_status": "active",
    "role": {"id": "role-public-uuid", "code": "property_manager", "version": 3}
  },
  "customer": null,
  "created_at": "2026-09-08T10:00:00Z",
  "updated_at": "2026-09-08T10:00:00Z"
}
```

客户账号的 `staff` 为 null，`customer` 返回：

```json
{
  "status": "prospect",
  "status_version": 1,
  "tenancy_version": 0,
  "first_prospect_at": "2026-09-08T10:00:00Z",
  "tenant_since": null,
  "former_tenant_at": null
}
```

### 2.2 TokenResponse

```json
{
  "data": {
    "access_token": "short-lived-token",
    "token_type": "Bearer",
    "expires_in": 900,
    "user": {},
    "scopes": ["iam:self:read"],
    "portal": "staff"
  }
}
```

登录、注册、refresh 同时设置 refresh cookie；响应体永远不返回 refresh token。

### 2.3 通用规则

- JSON 成功响应使用 `{"data": ...}`；列表增加 `meta.next_cursor`。
- 错误使用 [统一错误契约](README.md)：`error.code/message/request_id/retryable/details`。
- 写接口接收 `Idempotency-Key`；profile/password 等版本更新接收 `If-Match` 或 `version`。
- refresh/logout/password-reset 等 cookie 接口必须校验受信 Origin 和 `X-CSRF-Token`。
- 列表默认 `limit=50`，最大 200，使用 opaque cursor。

第一轮代码已落实版本冲突控制、refresh 双提交 CSRF、登录锁定、一次性 token 与内部事件
幂等。通用 HTTP `Idempotency-Key` 持久化重放、受信 Origin 白名单、验证码/网关级 IP 限流
以及真实邮件投递属于部署加固项；在这些能力接入前，表内相应文字是必须保留的接口约束，
不应被视为当前 runtime 已提供的安全控制。

## 3. 权限编码

权限校验以 permission 为准，不直接硬编码角色。`manager_admin` 默认拥有全部管理权限。

| Permission | 含义 |
|---|---|
| `iam:self:read` | 读取自己的身份资料 |
| `iam:self:update` | 修改自己的允许字段 |
| `iam:self:password_change` | 修改自己的密码 |
| `iam:self:sessions_manage` | 查看和撤销自己的登录设备 |
| `iam:user:read` | 查询用户身份与状态 |
| `iam:user:status_manage` | 暂停、恢复或删除账号 |
| `iam:staff:create` | 创建员工账号 |
| `iam:staff:read` | 查询员工档案 |
| `iam:staff:employment_manage` | 管理员工雇佣状态 |
| `iam:staff:role_manage` | 调整员工当前角色 |
| `iam:customer:read` | 查询客户身份阶段 |
| `iam:customer_status:read` | 查看客户阶段事件 |
| `rbac:read` | 查看角色和权限 |
| `rbac:manage` | 变更角色权限和状态 |
| `iam:service_client:manage` | 管理机器客户端元数据 |
| `iam:audit:read` | 查询脱敏身份审计 |
| `agent:staff:use` | 所有 active staff 进入员工 Agent 页面 |
| `property:read_market` | 查看市场/空置房源投影 |
| `prospect:manage` | 管理本人被分配的潜客 case 和真人联系线程 |
| `application:manage` | 审核本人被分配 case 下的租房申请 |
| `lease:prepare` | 从有权 approved application 准备合同 |
| `lease:execute` | 公司签署并执行有权合同 |
| `building:read_assigned` | 查看本人有效 building scope |
| `property:manage_assigned` | 查看并管理本人 scope 内房源；P0 页面仅使用读取投影 |
| `lease:manage_active_assigned` | 查看本人 scope 内在租合同和履约摘要 |
| `maintenance:assign_assigned` | 在本人 scope 内分派或改派维修工单 |
| `maintenance:update_assigned` | 在本人 scope 内接管、完成或取消维修工单 |
| `work_order:read_assigned` | 查看分配给本人的维修工单 |
| `work_order:update_assigned` | 推进分配给本人的维修工单状态 |
| `work_order:evidence_write` | 添加工单工作记录/证据 |
| `property:read_work_context` | 读取完成本人工单所需的最小房源上下文 |
| `report:read_work_context` | 读取完成本人工单所需的最小报告片段 |
| `report:read_assigned` | Property Manager 查看 scope 内 property 报告 |
| `report:generate_assigned` | Property Manager 为 scope 内 property 生成报告 |
| `report:read_all` | Manager Admin 查看任意 property 报告 |
| `report:generate_all` | Manager Admin 为任意 property 生成报告 |
| `building:read_all` | Manager Admin 查看全部 building |
| `property:read_all` | Manager Admin 查看全部 property 管理投影 |
| `prospect:manage_all` | Manager Admin 查看和改派全部 prospect case |
| `application:manage_all` | Manager Admin 查看和处理全部租房申请 |
| `lease:manage_all` | Manager Admin 查看、终止或补偿处理全部租约 |
| `maintenance:manage_all` | Manager Admin 查看、分派或处理全部维修工单 |
| `scope:manage` | 管理员工 building/property scope；P0 无编辑页面 |

`iam:manage` 可以作为管理员角色的权限集合标签，但 Controller 必须校验上表的具体权限。

### 3.1 P0 员工角色权限基线

下表是目标 Identity migration 的 role-permission seed 契约；实现阶段必须让现有 migration 与其
完全对齐。`manager_admin` 取其专属 IAM 权限与其他三种角色权限的并集；领域服务仍要叠加资源
scope/assignment，不能只凭 role code 放行。P0 UI 只调用第 3.1 节页面矩阵需要的权限，已预留的
管理权限不扩大 P0 页面范围。

| Role | P0 permissions |
|---|---|
| `leasing_consultant` | `property:read_market`, `prospect:manage`, `application:manage`, `lease:prepare`, `lease:execute`, `agent:staff:use` |
| `property_manager` | `building:read_assigned`, `property:manage_assigned`, `lease:manage_active_assigned`, `maintenance:assign_assigned`, `maintenance:update_assigned`, `report:read_assigned`, `report:generate_assigned`, `agent:staff:use` |
| `maintainer` | `work_order:read_assigned`, `work_order:update_assigned`, `work_order:evidence_write`, `property:read_work_context`, `report:read_work_context`, `agent:staff:use` |
| `manager_admin` | 上述领域权限并集 + `building:read_all`, `property:read_all`, `prospect:manage_all`, `application:manage_all`, `lease:manage_all`, `maintenance:manage_all`, `report:read_all`, `report:generate_all`, `iam:user:read`, `iam:user:status_manage`, `iam:staff:create`, `iam:staff:read`, `iam:staff:employment_manage`, `iam:staff:role_manage`, `iam:audit:read`, `rbac:read`, `rbac:manage`, `scope:manage` |

`*_all` 是 Manager Admin 的显式公司级资源权限，不需要伪造 building/property scope；领域服务仍须
校验动作状态机、版本和审计。其他三个角色没有 `*_all`，必须继续命中 assignment/scope。

## 4. 健康检查 API（2 个）

| 方法与路径 | 入参 | 成功返回 | 权限 |
|---|---|---|---|
| `GET /health/live` | 无 | `200 {"status":"ok","service":"identity-access"}` | Public |
| `GET /health/ready` | 无 | `200 {"status":"ready"}`；DB/迁移不可用时 503 | 仅内部网络/平台探针 |

## 5. 注册、登录与令牌 API（11 个）

| 方法与路径 | 入参 | 成功返回 | 权限 |
|---|---|---|---|
| `POST /api/v1/auth/guest-sessions` | `device_id?`、`locale?`；`Idempotency-Key` | `201` guest access token、过期时间、guest session ID、公开 scopes | Public；IP/device 限流 |
| `POST /api/v1/auth/register` | `email`、`username`、`password`、`guest_session_id?`、`locale?`、`accepted_terms_version`；`Idempotency-Key` | `201 TokenResponse`；customer/prospect，`portal=tenant` | Public；验证码与限流 |
| `POST /api/v1/auth/login` | `email`、`password`、`device_label?`、`remember_me=false` | `200 TokenResponse`；根据 account_type 返回 staff/tenant portal | Public；账号/IP 组合限流 |
| `POST /api/v1/auth/refresh` | HttpOnly refresh cookie、`X-CSRF-Token` | `200 TokenResponse`，rotation refresh cookie | active refresh token + active session |
| `POST /api/v1/auth/logout` | refresh cookie、`X-CSRF-Token`；Authorization 可选 | `204` 并清除 cookie | 当前 session；幂等 |
| `POST /api/v1/auth/logout-all` | Authorization、`X-CSRF-Token`、`current_password` | `204`；撤销全部 session，auth_version+1 | active user |
| `POST /api/v1/auth/email-verification/request` | 已登录无 body；未登录重发可传 `email` | `202 {"data":{"accepted":true}}` | Public + 限流；不泄漏邮箱存在性 |
| `POST /api/v1/auth/email-verification/confirm` | `token` | `200 {"data":{"email_verified":true}}` | 一次性 email token |
| `POST /api/v1/auth/password-reset/request` | `email`、`locale?` | `202 {"data":{"accepted":true}}` | Public + 严格限流 |
| `POST /api/v1/auth/password-reset/confirm` | `token`、`new_password` | `204`；撤销 sessions，auth_version+1 | 一次性 reset token |
| `POST /api/v1/auth/staff-activation/confirm` | `token`、`new_password`、`device_label?` | 兼容接口；P0 seed 流程不调用 | 非本期 UI |

登录失败统一返回 `invalid_credentials`，不能暴露邮箱是否存在。锁定账号使用
`account_temporarily_locked`；refresh token 重放必须撤销整个 token family 和 session，并返回
`refresh_token_reused`。注册固定创建 `account_type=customer` 与 `customer_status=prospect`，
客户端不能提交这两个字段。

## 6. 当前用户与会话 API（8 个）

| 方法与路径 | 入参 | 成功返回 | 权限 |
|---|---|---|---|
| `GET /api/v1/me` | Authorization | `200 UserView + scopes` | `iam:self:read`；本人 |
| `PATCH /api/v1/me/profile` | `username?`、`avatar?`、`locale?`、`version` | `200 UserView` | `iam:self:update`；本人 |
| `POST /api/v1/me/password` | `current_password`、`new_password` | `204`；撤销其他 sessions | `iam:self:password_change`；本人 |
| `GET /api/v1/me/sessions` | `cursor?`、`limit?` | `200 SessionView[]` | `iam:self:sessions_manage`；本人 |
| `DELETE /api/v1/me/sessions/{session_id}` | public session ID | `204` | `iam:self:sessions_manage`；本人设备 |
| `GET /api/v1/me/auth-events` | `cursor?`、`event_type?` | 脱敏的本人安全事件 | `iam:self:read`；本人 |
| `DELETE /api/v1/me/account` | `current_password`、`reason?`、`version`；幂等键 | `202 DeletionRequestView`；立即撤销全部 session | active customer 本人；staff 禁止自助删除 |
| `GET /api/v1/me/permissions` | Authorization | role/scopes/version 或 customer scopes/status_version | `iam:self:read`；本人 |

`PATCH /me/profile` 不能修改 email、account_type、role、customer_status 或
employment_status。邮箱变更如后续需要，必须建立带重新验证和唯一性确认的专用流程。

SessionView：

```json
{
  "id": "session-public-uuid",
  "device_label": "Chrome on macOS",
  "status": "active",
  "current": true,
  "last_seen_at": "2026-09-08T10:00:00Z",
  "expires_at": "2026-10-08T10:00:00Z"
}
```

## 7. 用户、员工与客户管理 API（15 个）

### 7.1 用户管理（5 个）

| 方法与路径 | 入参 | 成功返回 | 权限 |
|---|---|---|---|
| `GET /api/v1/iam/users` | `account_type?`、`status?`、`q?`、`cursor?`、`limit?` | 最小 UserSummary 列表 | `iam:user:read` |
| `GET /api/v1/iam/users/{user_id}` | public user ID | 按权限裁剪的 UserView | `iam:user:read` |
| `PATCH /api/v1/iam/users/{user_id}/status` | `status`、`reason`、`version` | 更新后的 UserView | `iam:user:status_manage` |
| `GET /api/v1/iam/users/{user_id}/auth-events` | `event_type?`、`cursor?`、`limit?` | 脱敏事件列表 | `iam:audit:read` |
| `POST /api/v1/iam/users/{user_id}/revoke-sessions` | `reason`；`Idempotency-Key` | `204` | `iam:user:status_manage` |

账号状态接口必须阻止停用/删除最后一位 active manager_admin。

### 7.2 员工管理（7 个）

| 方法与路径 | 入参 | 成功返回 | 权限 |
|---|---|---|---|
| `POST /api/v1/iam/staff` | `email`、`username`、`display_name`、`staff_code`、`role_id`、`hired_at?`；`Idempotency-Key` | 兼容管理接口，创建 pending；非本期 UI | `iam:staff:create` |
| `GET /api/v1/iam/staff` | `role?`、`employment_status?`、`q?`、cursor | StaffSummary 列表 | `iam:staff:read` |
| `GET /api/v1/iam/staff/{staff_id}` | public staff ID | StaffView | `iam:staff:read` |
| `POST /api/v1/iam/staff/{staff_id}/activation` | `reason?`；`Idempotency-Key` | 兼容接口；P0 seed 流程不调用 | 非本期 UI |
| `PATCH /api/v1/iam/staff/{staff_id}/employment` | `employment_status`、`effective_at`、`reason`、`version` | StaffView | `iam:staff:employment_manage` |
| `PATCH /api/v1/iam/staff/{staff_id}/role` | `role_id`、`reason`、`version`；`Idempotency-Key` | StaffView | `iam:staff:role_manage` |
| `GET /api/v1/iam/staff/{staff_id}/role-history` | cursor | StaffRoleHistory[] | `iam:staff:read` |

P0 不通过以上接口创建员工，而由 `IDENTITY_SEED_STAFF=true` 的非生产启动任务幂等创建 12 个
active staff。初始化明文仅作为输入，写库前使用与登录一致的 Argon2id；重复启动不新增账号、
不重置密码，生产环境强制拒绝该开关。变更 role 或 employment 必须递增 auth_version；角色接口
不能移除最后一位 active manager_admin。

### 7.3 客户身份查询（3 个）

| 方法与路径 | 入参 | 成功返回 | 权限 |
|---|---|---|---|
| `GET /api/v1/iam/customers` | `customer_status?`、`q?`、cursor | CustomerSummary 列表 | `iam:customer:read` |
| `GET /api/v1/iam/customers/{customer_id}` | customer public user ID | UserView/customer profile | `iam:customer:read` |
| `GET /api/v1/iam/customers/{customer_id}/status-events` | cursor | CustomerStatusEvent[] | `iam:customer_status:read` |

不存在管理员直接修改 `customer_status` 的外部接口。该状态只能由经过验证的租赁领域事件
更新，避免把业务事实改成手工标签。

## 8. 角色与权限 API（5 个）

| 方法与路径 | 入参 | 成功返回 | 权限 |
|---|---|---|---|
| `GET /api/v1/iam/roles` | `status?`、cursor | RoleSummary[] | `rbac:read` |
| `GET /api/v1/iam/roles/{role_id}` | public role ID | RoleView + permissions | `rbac:read` |
| `GET /api/v1/iam/permissions` | `risk_level?`、cursor | PermissionView[] | `rbac:read` |
| `PUT /api/v1/iam/roles/{role_id}/permissions` | `permission_codes[]`、`reason`、`version`；`Idempotency-Key` | RoleView，version+1 | `rbac:manage` |
| `PATCH /api/v1/iam/roles/{role_id}/status` | `status`、`reason`、`version` | RoleView | `rbac:manage` |

系统 role code 不可删除或改名。权限变化必须递增 `roles.version`、写审计并使高风险接口的
旧版本授权失败。

## 9. 机器客户端与审计 API（5 个）

| 方法与路径 | 入参 | 成功返回 | 权限 |
|---|---|---|---|
| `GET /api/v1/iam/service-clients` | `status?`、cursor | 不含密钥的客户端列表 | `iam:service_client:manage` |
| `POST /api/v1/iam/service-clients` | `client_code`、`credential_ref`、`allowed_audiences[]`、`allowed_scopes[]`、`key_id?` | `201 ServiceClientView` | `iam:service_client:manage` |
| `PATCH /api/v1/iam/service-clients/{client_code}` | audiences/scopes/status/key_id/version | ServiceClientView | `iam:service_client:manage` |
| `POST /api/v1/iam/service-clients/{client_code}/rotate` | `credential_ref`、`key_id`；`Idempotency-Key` | ServiceClientView | `iam:service_client:manage` |
| `GET /api/v1/iam/audit-events` | actor/user/type/time/cursor 过滤 | 脱敏 AuditEvent[] | `iam:audit:read` |

`credential_ref` 是密钥系统引用，不是 client secret；任何响应都不返回真实密钥。

## 10. 服务内部 API（8 个）

内部接口不通过公网 Gateway 暴露。权限是“有效 service identity + audience + allowed scope”，
并记录调用服务和原始 actor。

| 方法与路径 | 入参 | 成功返回 | 所需服务权限 |
|---|---|---|---|
| `POST /internal/v1/tokens/exchange` | service token、用户 token、`target_audience`、`requested_scopes[]` | ≤5 分钟委派 token | `identity:token_exchange`；scope 为三方交集 |
| `POST /internal/v1/tokens/introspect` | `token`、`required_audience?` | active、subject、actor、versions、scopes | `identity:token_introspect` |
| `GET /internal/v1/subjects/{subject_id}` | public subject ID、`fields?` | 最小 SubjectProjection | `identity:subject_read` |
| `POST /internal/v1/subjects/batch` | `subject_ids[]`，最多 200 | SubjectProjection[] | `identity:subject_read` |
| `POST /internal/v1/customer-status-events` | `event_id,customer_subject_id,lease_id,event_type=customer.tenancy_status_changed.v1,to_status=tenant|former_tenant,aggregate_version,occurred_at,details_redacted` | `202 accepted/duplicate/stale` | 仅 property-leasing 的 `identity:customer_status_write` |
| `POST /internal/v1/subject-deletions/{request_id}/acknowledgements` | `service,status=completed|failed,details_redacted?`；幂等 | `202 accepted|duplicate` | 仅约定领域 service identity |
| `GET /internal/v1/subject-deletions/{request_id}` | 无 | 各服务 acknowledgement、attempt、状态；不返回已删除 PII | `identity:subject_deletion_read` |
| `POST /internal/v1/subject-tombstones:check` | `subject_id` | `deleted=true|false,deletion_completed_at?`；不返回 fingerprint | 仅受信领域服务；可能重建 subject 关联的迟到/重放事件写入前必须检查，依赖不可用时 fail-closed |

服务 token 不接受浏览器直接获取；无用户触发的 worker 使用纯 service context，用户代办使用
`act.sub` 保存原始用户主体。

## 11. 接口总数与第一轮实现优先级

| 分组 | 数量 | 第一轮迁移优先级 |
|---|---:|---|
| 健康检查 | 2 | P0 |
| 注册、登录与令牌 | 11 | login/register/refresh/logout 为 P0；activation/验证/重置为兼容或 P1 |
| 当前用户与会话 | 8 | P0 |
| 用户、员工、客户管理 | 15 | P0 使用 seed；运行期创建/激活页面为 P1 |
| 角色与权限 | 5 | P0 read，P1 manage |
| 机器客户端与审计 | 5 | P1 |
| 服务内部 | 8 | P0 已实现，包括 subject deletion acknowledgement/status 和 Tombstone check |
| **合计** | **54（均已实现）** | P0 建立双端登录、员工种子、客户阶段和删除闭环 |

### P0 必须完成的用户闭环

1. customer register → customer login → me/profile/password/session/logout/refresh；
2. identity seed → 12 个 active staff 使用约定邮箱和密码登录；
3. staff login → 返回 staff portal、role、permission version；
4. Portal/Agent token exchange → 下游服务获得 audience 限定 actor context；
5. suspend/role/employment/password 变化 → 旧 session/token 失效。

## 12. Schema 实现状态

第一轮 migration 保留统一 `account_action_tokens` 表用于未来邮箱验证、找回/重置密码和兼容的
员工激活，但 P0 员工 seed 不创建或消费 action token：

| 字段 | 规则 |
|---|---|
| `id`、`public_id`、`user_id` | identity_access 内部 FK |
| `purpose` | `email_verify/password_reset/staff_activate` |
| `token_hash` | 唯一，只存高熵 token 哈希 |
| `expires_at`、`used_at?`、`revoked_at?` | 一次性和过期控制 |
| `requested_ip_hash?`、`created_at` | 风控与审计 |

同一 user + purpose 最多一个 active token；数据库只保存 SHA-256 token hash。员工初始化密码
写入 `user_credentials` 前使用 Argon2id，不保存可解密密码或明文日志。

账号删除闭环新增：

```text
subject_deletion_tombstones
- deletion_request_id UUID PRIMARY KEY
- subject_fingerprint BYTEA NOT NULL UNIQUE
- fingerprint_version SMALLINT NOT NULL
- status TEXT NOT NULL CHECK (status = 'completed')
- completed_at TIMESTAMPTZ NOT NULL
```

写入 Tombstone 与删除最后一批 Identity 可识别资料必须处于同一数据库事务。检查接口接收原始
subject_id 后仅在服务内按当前及仍受支持的历史 pepper version 计算 HMAC 并查唯一索引；响应不返回
fingerprint。Tombstone 不设置业务级 DELETE API。

## 13. 明确不提供的接口

- `/auth/switch-context`：一个账号首期不能同时是 staff 和 customer。
- customer 自助提交 `account_type` 或 staff role：防止越权注册。
- 直接修改 customer_status：状态来自租约事实。
- 修改系统 role code、删除 permission：避免契约漂移。
- 返回 password/refresh/service secret：任何权限下都禁止。

## 14. Portal 用户使用逻辑

本节把已经实现的 Identity 接口组合成可直接供双端前端使用的完整流程。Portal API 不复制
Identity 数据或令牌逻辑；Gateway 将 `/api/v1/auth/*`、`/api/v1/me*`、`/api/v1/iam/*`
直接路由到本服务。

### 14.1 应用冷启动

1. 浏览器不得把 access token 写入 localStorage/sessionStorage；只保存在运行内存。
2. 页面冷启动若存在 refresh cookie，调用 `POST /api/v1/auth/refresh`，携带受信 Origin 和
   `X-CSRF-Token`。
3. 成功后按 `portal` 跳转，再调用 `/api/v1/me` 或相应 Portal bootstrap。
4. refresh 返回 401 时清除本地登录态并进入登录页，不循环重试。
5. 同一页面多个请求同时遇到 access token 过期时，只允许一个 single-flight refresh；其他请求
   等待结果，避免 refresh rotation 被旧 token 并发重放。

### 14.2 Customer 注册与登录

1. Guest 无 Identity 账号即可浏览公开房源；guest session 端点保留但不是 P0 浏览前置条件。
2. 注册页面只提交 email、username、password、locale、条款版本和可选 guest session ID。
3. Identity 固定创建 active customer + prospect profile；前端不得提交 account_type/status。
4. 注册成功即建立 auth session并返回 `portal=tenant`。
5. 后续 Leasing 消费事实触发的 customer status event；Portal 不提供手工“升级租客”按钮。

### 14.3 Staff 初始化与首次使用

1. Alembic 先 seed 四种系统角色和基线权限。
2. 非生产 `identity-seed` 创建 4 名 Leasing Consultant、4 名 Property Manager、3 名
   Maintainer、1 名 Manager Admin；邮箱为 `{FirstName}Safescan@outlook.com`。
3. username 为 `FirstNameLastName`，初始化密码为 `staff{username}123456`；数据库只保存 Argon2id。
4. 12 个账号直接处于 active user + active employment，可通过统一登录进入 `/staff/`。
5. 重跑 seed 不重置密码；普通 staff 不可自助注册、改变 role/account_type 或删除账号。

P0 固定种子清单如下。表中的密码仅用于本地/演示环境首次登录，Identity 写库前统一使用
Argon2id 哈希，接口、日志和数据库均不得保存或返回明文：

| Staff code | Role | Display name | Username | Email | 初始化密码 |
|---|---|---|---|---|---|
| LC001 | Leasing Consultant | Ethan Carter | `EthanCarter` | `EthanSafescan@outlook.com` | `staffEthanCarter123456` |
| LC002 | Leasing Consultant | Olivia Bennett | `OliviaBennett` | `OliviaSafescan@outlook.com` | `staffOliviaBennett123456` |
| LC003 | Leasing Consultant | Liam Foster | `LiamFoster` | `LiamSafescan@outlook.com` | `staffLiamFoster123456` |
| LC004 | Leasing Consultant | Sophia Reed | `SophiaReed` | `SophiaSafescan@outlook.com` | `staffSophiaReed123456` |
| PM001 | Property Manager | Noah Mitchell | `NoahMitchell` | `NoahSafescan@outlook.com` | `staffNoahMitchell123456` |
| PM002 | Property Manager | Emma Collins | `EmmaCollins` | `EmmaSafescan@outlook.com` | `staffEmmaCollins123456` |
| PM003 | Property Manager | James Parker | `JamesParker` | `JamesSafescan@outlook.com` | `staffJamesParker123456` |
| PM004 | Property Manager | Ava Richardson | `AvaRichardson` | `AvaSafescan@outlook.com` | `staffAvaRichardson123456` |
| MT001 | Maintainer | Daniel Cooper | `DanielCooper` | `DanielSafescan@outlook.com` | `staffDanielCooper123456` |
| MT002 | Maintainer | Grace Turner | `GraceTurner` | `GraceSafescan@outlook.com` | `staffGraceTurner123456` |
| MT003 | Maintainer | Henry Walker | `HenryWalker` | `HenrySafescan@outlook.com` | `staffHenryWalker123456` |
| MA001 | Manager Admin | Charlotte Morgan | `CharlotteMorgan` | `CharlotteSafescan@outlook.com` | `staffCharlotteMorgan123456` |

### 14.4 登录判断

登录只按规范化 email 找唯一 user：

- 不存在或密码错误统一 `invalid_credentials`，避免枚举邮箱；
- 连续失败达到阈值进入临时锁定；
- user 非 active 拒绝；
- staff 还必须满足 employment active 和 role active；
- customer 使用当前 customer profile 生成 status/scopes；
- 服务返回的 `portal` 是唯一跳转依据，客户端不能要求切换身份。

### 14.5 Token、会话和退出

- access token 短期存在内存；普通请求使用 Bearer token。
- refresh token 是 opaque cookie，每次 refresh rotation；数据库只存 hash。
- 普通退出撤销当前 session；logout-all 校验当前密码，撤销全部 session 并递增 auth_version。
- 改密保留当前设备、撤销其他设备；重置密码撤销全部设备。
- refresh token 重放撤销整个 family/session，并记录安全事件。
- role、employment、账号状态和 customer status 变化后递增版本；旧 token 在鉴权时返回
  `token_stale`。

### 14.6 与领域服务的衔接

- Portal/领域服务验证 JWT audience，不使用一个全平台通用 token。
- Portal 调用 `/internal/v1/tokens/exchange` 获得目标服务的短期委派 token。
- token 中 role/customer_status/scopes 只是权限上限；Property Leasing、Maintenance 和 Report
  必须继续校验 scope、case、assignment、本人承租关系、Lease 状态和报告 `source_lease_id`。
- Property Leasing 通过 `customer.tenancy_status_changed.v1` 向内部端点提交权威 `to_status`、
  `lease_id` 和递增 `aggregate_version`。Identity 拒绝非法转换、重复或乱序事件，状态变化时递增
  status/auth version，使旧 token 失效。Identity 不保存或校验租约 count；一人同时只有一个当前
  租约由 Property Leasing 的数据库 slot 唯一约束保证。

### 14.7 Customer scope 矩阵

| 状态 | Identity 基础 scope |
|---|---|
| prospect | `property:read_market,application:self:read/create/submit,prospect:self:manage` |
| tenant | `property:read_market,application:self:read,lease:self:read,maintenance:self:create,report:self:create/read` |
| former_tenant | prospect 的申请能力 + `lease:self:read_history,report:self:read_history` |

Identity scope 只表达能力上限。Tenant 创建或查看当前报告时 Report Service 仍须向 Leasing 核验
当前唯一租约状态为 active 且 property 匹配；executed 待入住阶段即使 token 已是 tenant 也不能
报修或访问报告。Former Tenant 的历史合同权限须命中本人历史 lease/property 关系；报告读取还须
满足 `report.source_lease_id` 等于该历史 Lease。

### 14.8 Customer 账号删除

1. DELETE account 验证当前密码和 version，并同时调用 Property Leasing 与 Maintenance 做初次
   eligibility check；pending_signature/executed/active lease 返回
   `409 active_lease_blocks_deletion`，open/assigned/in_progress/blocked 工单返回
   `409 open_maintenance_orders_block_deletion`。任一依赖超时或不可确认时返回 503 并 fail-closed。
2. 初检通过后创建唯一 deletion request，账号进入 `deletion_pending`，撤销全部 session、refresh
   family 并递增 auth_version。所有新的客户写命令必须验证该状态并拒绝提交。
3. 冻结账号后再次执行两项 eligibility check，以捕获初检期间已经在途并刚提交的业务写入。发现
   blocker 时 request 保持 `blocked`，worker 定期重查；只有复检无 blocker 才进入 `processing`。
   P0 不使用分布式锁或两阶段提交。
4. Identity 在同一事务写 `identity.subject_deletion_requested.v1` outbox；Leasing、Maintenance、
   Report 分别处理并回传 acknowledgement。
5. 未收到全部 completed 前账号不可登录但 Identity 保留最小编排记录；失败 acknowledgement 由
   worker 重试并告警。
6. 全部完成后删除 credential、session、profile 和可识别 user 数据，只保留正式 Tombstone：
   `deletion_request_id,subject_fingerprint,fingerprint_version,status,completed_at`。fingerprint 使用
   独立 `deletion_pepper` 对 subject_id 做 HMAC，不保存 subject_id/email/姓名且不通过业务 API 返回。
7. Tombstone 在系统生命周期内保留，用于重复删除幂等、受信服务的迟到事件检查和安全审计；密钥
   轮换按 fingerprint_version 验证。异步消费者在迟到/重放事件可能创建 subject 关联前必须先读取
   SubjectProjection 确认账号 active；账号不存在时再调用 Tombstone check。`deletion_pending`、
   Tombstone 命中或 Identity 不可用均 fail-closed，不得重新创建账号、profile、party 或其他关联。
8. DeletionRequestView 状态固定为 `checking|blocked|processing|completed|failed`；blocked 只返回本人
   可见的安全 blocker 摘要，不返回其他客户或内部数据。
9. 历史合同正常情况下永久保留，但用户主动删除账号是产品定义的唯一例外；正式商用前若法规
   要求合同留存，领域服务改做不可逆匿名化，并在部署策略中覆盖本默认行为。

### 14.9 Identity 错误码

HTTP、`retryable` 和 details 白名单以 [统一错误契约](README.md) 为唯一真相。本服务 P0 子码为：
`invalid_credentials`、`account_temporarily_locked`、`invalid_refresh_token`、
`refresh_token_expired`、`refresh_token_reused`、`account_unavailable`、
`staff_account_unavailable`、`email_already_exists`、`action_token_invalid`、`session_inactive`、
`customer_status_transition_invalid`、`account_deletion_pending`、`active_lease_blocks_deletion`、
`open_maintenance_orders_block_deletion`、`subject_already_deleted`、`version_conflict`、
`idempotency_conflict`、`csrf_invalid`、`dependency_unavailable`、`dependency_timeout`。

登录不存在的邮箱与密码错误必须使用同一 `invalid_credentials`；Tombstone fingerprint、密码规则
命中项、账号内部停用原因和下游响应 body 永不进入公共 details。

## 15. Redis、高并发与上线加固

### 15.1 可缓存内容

| 内容 | Key 要素 | TTL/失效 |
|---|---|---|
| JWKS/签名公钥 | issuer + kid | 5–15min；轮换主动刷新 |
| 低风险角色权限模板 | role ID + role version | 1–5min；role 更新 pub/sub 失效 |
| 短期 introspection active 结果 | token digest/jti + audience | 不超过 token 剩余有效期，建议 ≤60s |
| Subject 最小公开投影 | subject + projection version | 30–120s；user/status 事件失效 |
| API 限流 | IP/account/subject + route bucket | Redis 原子令牌桶/滑动窗口 |

不得缓存密码校验结果、refresh token 明文/hash、CSRF secret、一次性 action token、账号锁定写入
或高风险授权的无版本结论。role/employment/status 变更和 logout-all 应发布失效消息；缓存失效
消息丢失时由短 TTL 和数据库版本校验兜底。

### 15.2 建议限流基线

| 接口 | 建议默认值 | 维度 |
|---|---|---|
| login | 5/min、30/hour | account hash + IP；成功后适度清零 |
| register | 5/hour | IP + device |
| guest session | 30/hour | IP + device |
| refresh | 30/min | session + IP |
| password reset | 3/hour | email hash + IP |
| email verification | 5/hour | user/email hash + IP |
| token introspection/exchange | 按 service client 配额 | client + audience |

限流必须使用 Redis/Gateway 等共享存储，不使用每个进程独立计数。达到限制返回 429、稳定
`rate_limited` 和安全的 `Retry-After`。

### 15.3 一致性和故障策略

- 登录锁定、refresh rotation、session revoke、action token consume 仍以 PostgreSQL 行锁/事务为
  权威，不能只写 Redis。
- Redis 不可用时登录可按数据库风控降级并收紧网关限流；refresh/session 正确性不得改变。
- 高风险接口遇到版本缓存无法确认时回源或失败关闭。
- 通用 `Idempotency-Key` 必须落持久记录；Redis 仅作为快速重复请求合并层。
- Argon2id 是 CPU/内存密集工作，应限制登录 worker 并发，监控 event loop/线程池排队，不能
  为追求吞吐降低到不安全哈希参数。

### 15.4 现有实现与上线差距

当前代码已经实现账号模型、Argon2id、12 人非生产 seed、登录锁定、session、refresh
rotation/replay、RBAC、客户租期事件版本和内部 token/subject 接口。以下仍是上线前必须完成的
加固项：

- 受信 Origin 白名单和完整 cookie/CSRF 部署配置；
- 共享 Redis/Gateway 限流，而非仅接口文字约束；
- 通用写接口持久化 Idempotency-Key 重放；
- P1 启用邮件/通知前完成 action token 交付与泄漏检查；
- 非对称 JWT/JWKS 的生产密钥轮换（当前开发配置仍使用共享 secret 时不得按生产发布）；
- 登录、refresh、锁定、重放和管理员操作的告警与审计留存。

## 16. 双端 Identity 验收

1. Customer 注册后固定为 prospect 并进入 tenant Portal。
2. 12 个 seed staff 数量/角色/邮箱准确，均可登录 staff Portal，数据库无明文密码。
3. 客户端提交 account_type、role 或 customer_status 均不改变服务端身份。
4. 五次失败锁定、统一错误、refresh rotation/replay、logout-all 和改密会话策略通过。
5. role/employment/customer status 变化后旧 token 不再用于敏感操作。
6. 两个并发 refresh 只能有一个有效后继；重放触发 token family 撤销。
7. Redis 不可用不会跳过密码、session、版本或 audience 校验。
8. `prospect/former_tenant→tenant→former_tenant` 合法；除同 event_id 幂等重放外，非法重复转换、
   非法 `to_status` 和乱序 aggregate version 均被拒绝。
9. account deletion 立即撤销登录；各服务 acknowledgement 可重放，未全部完成不得删除编排记录。
10. 非终态维修工单阻止删除；全部完成/取消后同一删除请求可安全重试。
11. 删除完成后 Tombstone 不含 subject/email；迟到事件命中后不会重新创建任何用户关联。
