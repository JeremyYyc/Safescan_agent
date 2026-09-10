# identity-access-service

## 职责

负责唯一登录身份、凭据、员工档案、客户阶段、角色权限、登录会话、刷新令牌和机器身份。
它签发身份上下文，但不决定房源、租约、工单或报告的业务状态。

## 数据所有权

`users`、`user_credentials`、`staff`、`staff_role_history`、`roles`、`permissions`、
`role_permissions`、`customer_profiles`、`customer_status_events`、`auth_sessions`、
`refresh_tokens`、`account_action_tokens`、`guest_sessions`、`service_clients`、`auth_events`，以及本 schema 的
`outbox_events` / `inbox_events`。

## 已落地模块

- Controllers：auth、me、IAM 管理、内部 token/subject/Leasing Consultant/event 接口。
- Services：注册登录、一次性 action token、refresh rotation、员工生命周期、RBAC、客户状态投影。
- Mappers：User、Credential、Staff、Role、Session、ServiceClient、AuthEvent。
- Runtime：独立 Dockerfile、Compose healthcheck、Nginx 外部路由；内部接口不进入 Gateway。
- 公共基础设施：HTTP 错误/响应/Request ID、数据库 session factory、JWT 消费端/Principal/
  scope 校验及 cursor 分页来自 `safescan-common`；Identity 仅保留配置组合层和领域实现。

完整接口、入参、返回和权限见
[Identity Access Service API 契约清单](../api/identity-access-api.md)。

## 关键约束与测试

- 邮箱规范化后全局唯一，一个账号只能是 staff 或 customer。
- 密码只保存强哈希，refresh token 只保存哈希并检测重放。
- 角色或雇佣状态变化必须递增授权版本并撤销旧会话。
- 阻止停用最后一个 active `manager_admin`。
- 单元/API 契约测试验证 56 个操作、JWT audience/scope、Leasing Consultant 最小投影、Argon2id 与 opaque cursor。
- Docker smoke 在空 PostgreSQL 上验证 migration downgrade/upgrade、12 名员工 seed 与逐一登录，
  并覆盖 customer 注册、refresh rotation/replay、`/me` 和 logout 后会话失效。
