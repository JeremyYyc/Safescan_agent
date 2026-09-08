# Identity Access Service API 契约清单

- 状态：第一轮已实现（51 个 OpenAPI operations）
- 版本：v1
- 外部前缀：`/api/v1`
- 服务内部前缀：`/internal/v1`
- 容器监听端口：`8000`（仅 Compose 内网，不发布宿主机端口）
- 数据所有者：`identity-access-service`

本文是第一轮 Identity Service 代码迁移的接口契约。它从 `identity_access` schema、员工
RBAC、客户状态和双端登录流程反推，现由独立的
`backend/services/identity-access-service` 实现；旧 `backend/app/api/auth.py` 仅作为迁移期
兼容入口，不代表新服务的代码边界。

## 1. 核心产品决策

1. 员工端和客户端共用 `POST /api/v1/auth/login`，服务根据唯一账号的 `account_type`
   返回 `portal=staff|tenant`；前端不能提交或切换身份。
2. 公共注册只能创建 `customer + prospect`。员工不能自助注册，只能由拥有
   `iam:staff:create` 的管理员创建并激活。
3. access token 是短期、audience 限定 token，通过响应体返回并只保存在浏览器内存。
4. refresh token 是 opaque 随机值，只放在 `Secure + HttpOnly + SameSite` cookie；数据库
   只保存哈希，每次 refresh 都 rotation。
5. token 中的 role/customer_status 是权限上限；具体房源、租约、工单和报告仍由对应领域
   服务做资源授权。
6. 所有对外 ID 都是 public UUID；任何接口都不返回 bigint 主键、密码哈希或 refresh token
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
- 错误使用 [统一错误契约](README.md)：`error.code/message/request_id/details`。
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

`iam:manage` 可以作为管理员角色的权限集合标签，但 Controller 必须校验上表的具体权限。

## 4. 健康检查 API（2 个）

| 方法与路径 | 入参 | 成功返回 | 权限 |
|---|---|---|---|
| `GET /health/live` | 无 | `200 {"status":"ok","service":"identity-access"}` | Public |
| `GET /health/ready` | 无 | `200 {"status":"ready"}`；DB/迁移不可用时 503 | 仅内部网络/平台探针 |

## 5. 注册、登录与令牌 API（11 个）

| 方法与路径 | 入参 | 成功返回 | 权限 |
|---|---|---|---|
| `POST /api/v1/auth/guest-sessions` | `device_id?`、`locale?`；`Idempotency-Key` | `201` guest access token、过期时间、guest session ID、公开 scopes | Public；IP/device 限流 |
| `POST /api/v1/auth/register` | `email`、`username`、`password`、`guest_session_id?`、`locale?`、`accepted_terms_version`；`Idempotency-Key` | `201 TokenResponse`；customer/prospect/tenant portal | Public；验证码与限流 |
| `POST /api/v1/auth/login` | `email`、`password`、`device_label?`、`remember_me=false` | `200 TokenResponse`；根据 account_type 返回 staff/tenant portal | Public；账号/IP 组合限流 |
| `POST /api/v1/auth/refresh` | HttpOnly refresh cookie、`X-CSRF-Token` | `200 TokenResponse`，rotation refresh cookie | active refresh token + active session |
| `POST /api/v1/auth/logout` | refresh cookie、`X-CSRF-Token`；Authorization 可选 | `204` 并清除 cookie | 当前 session；幂等 |
| `POST /api/v1/auth/logout-all` | Authorization、`X-CSRF-Token`、`current_password` | `204`；撤销全部 session，auth_version+1 | active user |
| `POST /api/v1/auth/email-verification/request` | 已登录无 body；未登录重发可传 `email` | `202 {"data":{"accepted":true}}` | Public + 限流；不泄漏邮箱存在性 |
| `POST /api/v1/auth/email-verification/confirm` | `token` | `200 {"data":{"email_verified":true}}` | 一次性 email token |
| `POST /api/v1/auth/password-reset/request` | `email`、`locale?` | `202 {"data":{"accepted":true}}` | Public + 严格限流 |
| `POST /api/v1/auth/password-reset/confirm` | `token`、`new_password` | `204`；撤销 sessions，auth_version+1 | 一次性 reset token |
| `POST /api/v1/auth/staff-activation/confirm` | `token`、`new_password`、`device_label?` | `200 TokenResponse`；激活 user/staff 并进入 staff portal | 一次性 staff activation token |

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
| `DELETE /api/v1/me/account` | `current_password`、`reason?`、`version` | `202` | active customer 本人；staff 禁止自助删除 |
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
| `POST /api/v1/iam/staff` | `email`、`username`、`display_name`、`staff_code`、`role_id`、`hired_at?`；`Idempotency-Key` | `201 StaffView`，初始 pending | `iam:staff:create` |
| `GET /api/v1/iam/staff` | `role?`、`employment_status?`、`q?`、cursor | StaffSummary 列表 | `iam:staff:read` |
| `GET /api/v1/iam/staff/{staff_id}` | public staff ID | StaffView | `iam:staff:read` |
| `POST /api/v1/iam/staff/{staff_id}/activation` | `reason?`；`Idempotency-Key` | `202 {"data":{"accepted":true}}` | `iam:staff:create`；仅 pending staff |
| `PATCH /api/v1/iam/staff/{staff_id}/employment` | `employment_status`、`effective_at`、`reason`、`version` | StaffView | `iam:staff:employment_manage` |
| `PATCH /api/v1/iam/staff/{staff_id}/role` | `role_id`、`reason`、`version`；`Idempotency-Key` | StaffView | `iam:staff:role_manage` |
| `GET /api/v1/iam/staff/{staff_id}/role-history` | cursor | StaffRoleHistory[] | `iam:staff:read` |

创建员工时不接收明文初始密码。服务创建 pending 账号并发送一次性激活 token；激活完成后
才允许登录。变更 role 或 employment 必须递增 auth_version 并撤销需立即失效的 session；
角色接口同样不能移除最后一位 active manager_admin。

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

## 10. 服务内部 API（5 个）

内部接口不通过公网 Gateway 暴露。权限是“有效 service identity + audience + allowed scope”，
并记录调用服务和原始 actor。

| 方法与路径 | 入参 | 成功返回 | 所需服务权限 |
|---|---|---|---|
| `POST /internal/v1/tokens/exchange` | service token、用户 token、`target_audience`、`requested_scopes[]` | ≤5 分钟委派 token | `identity:token_exchange`；scope 为三方交集 |
| `POST /internal/v1/tokens/introspect` | `token`、`required_audience?` | active、subject、actor、versions、scopes | `identity:token_introspect` |
| `GET /internal/v1/subjects/{subject_id}` | public subject ID、`fields?` | 最小 SubjectProjection | `identity:subject_read` |
| `POST /internal/v1/subjects/batch` | `subject_ids[]`，最多 200 | SubjectProjection[] | `identity:subject_read` |
| `POST /internal/v1/customer-status-events` | `event_id`、`customer_subject_id`、`lease_id`、`event_type`、`occurred_at`、`details_redacted` | `202 accepted/duplicate` | 仅 property-leasing 的 `identity:customer_status_write` |

服务 token 不接受浏览器直接获取；无用户触发的 worker 使用纯 service context，用户代办使用
`act.sub` 保存原始用户主体。

## 11. 接口总数与第一轮实现优先级

| 分组 | 数量 | 第一轮迁移优先级 |
|---|---:|---|
| 健康检查 | 2 | P0 |
| 注册、登录与令牌 | 11 | login/register/refresh/logout/staff activation 为 P0；验证/重置为 P1 |
| 当前用户与会话 | 8 | P0 |
| 用户、员工、客户管理 | 15 | staff 创建/激活/查询/角色/雇佣和 user 状态为 P0，其余 P1 |
| 角色与权限 | 5 | P0 read，P1 manage |
| 机器客户端与审计 | 5 | P1 |
| 服务内部 | 5 | exchange/introspect/subject read 为 P0，事件消费为 P1 |
| **合计** | **51** | P0 建立双端可登录和可管理员工的最小闭环 |

### P0 必须完成的用户闭环

1. customer register → customer login → me/profile/password/session/logout/refresh；
2. manager admin login → create pending staff → activate staff → assign role/employment；
3. staff login → 返回 staff portal、role、permission version；
4. Portal/Agent token exchange → 下游服务获得 audience 限定 actor context；
5. suspend/role/employment/password 变化 → 旧 session/token 失效。

## 12. Schema 实现状态

第一轮 migration 已增加统一 `account_action_tokens` 表，用于邮箱验证、找回/重置密码和
员工首次激活：

| 字段 | 规则 |
|---|---|
| `id`、`public_id`、`user_id` | identity_access 内部 FK |
| `purpose` | `email_verify/password_reset/staff_activate` |
| `token_hash` | 唯一，只存高熵 token 哈希 |
| `expires_at`、`used_at?`、`revoked_at?` | 一次性和过期控制 |
| `requested_ip_hash?`、`created_at` | 风控与审计 |

同一 user + purpose 最多一个 active token；数据库只保存 SHA-256 token hash。不能复用 refresh token、把 token 明文存库或让
管理员设置可长期使用的临时密码。

## 13. 明确不提供的接口

- `/auth/switch-context`：一个账号首期不能同时是 staff 和 customer。
- customer 自助提交 `account_type` 或 staff role：防止越权注册。
- 直接修改 customer_status：状态来自租约事实。
- 修改系统 role code、删除 permission：避免契约漂移。
- 返回 password/refresh/service secret：任何权限下都禁止。
