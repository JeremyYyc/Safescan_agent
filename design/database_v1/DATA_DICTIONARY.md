# 数据字典（生成文件）

按服务 schema 划分；生产可独立数据库。仅服务内建立外键；跨服务 ID 为逻辑引用。
所有新增表除 organizations 外均有 organization_id。删除默认 NO ACTION。

## identity_access.organizations

物业运营组织；全部新增业务数据的隔离根

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| name | TEXT | 否 |  |  |
| code | TEXT | 否 |  |  |
| status | TEXT | 否 | 'active' | active / suspended |
| timezone | TEXT | 否 | 'Asia/Shanghai' |  |

约束与关联：

- UNIQUE code
- CHECK `status IN ('active','suspended')`

## identity_access.account_memberships

共享账号在组织中的身份；员工与租客身份可同时存在，角色由服务端验证

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| user_id | BIGINT | 否 |  |  |
| persona | TEXT | 否 |  | staff / tenant / prospect |
| status | TEXT | 否 | 'active' | active / inactive |

约束与关联：

- CHECK `status IN ('active','inactive')`
- CHECK `persona IN ('staff','tenant','prospect')`
- FK organization_id → identity_access.organizations.id
- UNIQUE organization_id, user_id, persona
- UNIQUE organization_id, id

## identity_access.permissions

权限目录，例如 maintenance:read；代码侧白名单解释

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| code | TEXT | 否 |  |  |
| description | TEXT | 否 |  |  |

约束与关联：

- UNIQUE organization_id, code
- UNIQUE organization_id, id
- FK organization_id → identity_access.organizations.id

## identity_access.roles

角色定义；业务权限与资源范围分别管理

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| code | TEXT | 否 |  |  |
| name | TEXT | 否 |  |  |

约束与关联：

- UNIQUE organization_id, id
- FK organization_id → identity_access.organizations.id
- UNIQUE organization_id, code

## identity_access.staff

员工身份；user_id 在集成脚本中连接现有 public.users

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| user_id | BIGINT | 是 |  |  |
| staff_code | TEXT | 否 |  |  |
| display_name | TEXT | 否 |  |  |
| status | TEXT | 否 | 'active' | active / inactive |

约束与关联：

- FK organization_id → identity_access.organizations.id
- UNIQUE organization_id, user_id
- UNIQUE organization_id, id
- UNIQUE organization_id, staff_code
- CHECK `status IN ('active','inactive')`

## identity_access.role_permissions

角色权限关联

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| role_id | BIGINT | 否 |  |  |
| permission_id | BIGINT | 否 |  |  |

约束与关联：

- FK organization_id, permission_id → identity_access.permissions.organization_id, identity_access.permissions.id
- UNIQUE organization_id, id
- FK organization_id, role_id → identity_access.roles.organization_id, identity_access.roles.id
- FK organization_id → identity_access.organizations.id
- UNIQUE organization_id, role_id, permission_id

## identity_access.staff_roles

员工角色关联

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| staff_id | BIGINT | 否 |  |  |
| role_id | BIGINT | 否 |  |  |

约束与关联：

- UNIQUE organization_id, staff_id, role_id
- FK organization_id, role_id → identity_access.roles.organization_id, identity_access.roles.id
- FK organization_id → identity_access.organizations.id
- FK organization_id, staff_id → identity_access.staff.organization_id, identity_access.staff.id
- UNIQUE organization_id, id

## property_leasing.parties

业主、租客、供应商主体；联系信息需服务层脱敏

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| kind | TEXT | 否 |  | owner / tenant / prospect / vendor |
| user_id | BIGINT | 是 |  |  |
| name | TEXT | 否 |  |  |
| contact | JSONB | 否 | '{}'::jsonb |  |

约束与关联：

- UNIQUE organization_id, id
- CHECK `kind IN ('owner','tenant','prospect','vendor')`
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## property_leasing.payments

实收支付；退款扩展为独立冲销流水，当前仅建收款框架

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| reference | TEXT | 否 |  |  |
| received_at | TIMESTAMP WITH TIME ZONE | 否 |  |  |
| amount | NUMERIC(14, 2) | 否 |  |  |
| currency | TEXT | 否 | 'AUD' |  |
| provider_reference | TEXT | 是 |  |  |

约束与关联：

- UNIQUE organization_id, id
- CHECK `amount > 0`
- UNIQUE organization_id, reference
- UNIQUE organization_id, provider_reference
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## property_leasing.properties

房源；设施和地理展示信息可扩展，授权不使用 JSON

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| reference | TEXT | 否 |  |  |
| address | TEXT | 否 |  |  |
| bedrooms | INTEGER | 否 |  |  |
| bathrooms | INTEGER | 否 |  |  |
| weekly_rent | NUMERIC(14, 2) | 否 |  |  |
| currency | TEXT | 否 | 'AUD' |  |
| status | TEXT | 否 | 'available' | available / occupied / unavailable |
| listing_visibility | TEXT | 否 | 'private' | private / public |
| attributes | JSONB | 否 | '{}'::jsonb |  |

约束与关联：

- CHECK `listing_visibility IN ('private','public')`
- CHECK `currency ~ '^[A-Z]{3}$'`
- CHECK `bathrooms >= 0`
- CHECK `bedrooms >= 0`
- UNIQUE organization_id, reference
- CHECK `weekly_rent >= 0`
- CHECK `status IN ('available','occupied','unavailable')`
- UNIQUE organization_id, id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## property_leasing.leases

租约；包含金额币种与有效日期

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| property_id | BIGINT | 否 |  |  |
| reference | TEXT | 否 |  |  |
| starts_on | DATE | 否 |  |  |
| ends_on | DATE | 否 |  |  |
| weekly_rent | NUMERIC(14, 2) | 否 |  |  |
| currency | TEXT | 否 | 'AUD' |  |
| status | TEXT | 否 | 'draft' | draft / active / expired / terminated |

约束与关联：

- CHECK `weekly_rent >= 0`
- UNIQUE organization_id, id
- CHECK `ends_on >= starts_on`
- UNIQUE organization_id, reference
- CHECK `status IN ('draft','active','expired','terminated')`
- CHECK `currency ~ '^[A-Z]{3}$'`
- FK organization_id, property_id → property_leasing.properties.organization_id, property_leasing.properties.id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## property_leasing.property_favorites

潜在租客收藏房源；已登录用户映射到本组织主体

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| party_id | BIGINT | 否 |  |  |
| property_id | BIGINT | 否 |  |  |

约束与关联：

- FK organization_id, property_id → property_leasing.properties.organization_id, property_leasing.properties.id
- UNIQUE organization_id, id
- UNIQUE organization_id, party_id, property_id
- FK organization_id, party_id → property_leasing.parties.organization_id, property_leasing.parties.id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## property_leasing.property_owners

房源与业主关联

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| property_id | BIGINT | 否 |  |  |
| party_id | BIGINT | 否 |  |  |
| share | NUMERIC(7, 6) | 否 |  |  |

约束与关联：

- UNIQUE organization_id, id
- FK organization_id, property_id → property_leasing.properties.organization_id, property_leasing.properties.id
- UNIQUE organization_id, property_id, party_id
- FK organization_id, party_id → property_leasing.parties.organization_id, property_leasing.parties.id
- CHECK `share > 0 AND share <= 1`
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## property_leasing.staff_property_scopes

员工可访问房源；权限码仍需单独验证

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| staff_id | BIGINT | 否 |  |  |
| property_id | BIGINT | 否 |  |  |
| valid_from | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| valid_until | TIMESTAMP WITH TIME ZONE | 是 |  |  |

约束与关联：

- UNIQUE organization_id, staff_id, property_id
- CHECK `valid_until IS NULL OR valid_until > valid_from`
- UNIQUE organization_id, id
- FK organization_id, property_id → property_leasing.properties.organization_id, property_leasing.properties.id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键
- 跨服务逻辑引用 staff_id → identity_access.staff.id；由 API / 事件校验，非数据库外键

## property_leasing.tenancy_applications

潜在租客申请；双方通过同一服务操作，禁止各自复制业务真相

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| property_id | BIGINT | 否 |  |  |
| applicant_id | BIGINT | 否 |  |  |
| reference | TEXT | 否 |  |  |
| status | TEXT | 否 | 'draft' | draft / submitted / under_review / approved / rejected / withdrawn |
| submitted_at | TIMESTAMP WITH TIME ZONE | 是 |  |  |
| version | INTEGER | 否 | 1 |  |

约束与关联：

- CHECK `status IN ('draft','submitted','under_review','approved','rejected','withdrawn')`
- FK organization_id, property_id → property_leasing.properties.organization_id, property_leasing.properties.id
- UNIQUE organization_id, reference
- CHECK `version > 0`
- FK organization_id, applicant_id → property_leasing.parties.organization_id, property_leasing.parties.id
- UNIQUE organization_id, id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## property_leasing.viewing_appointments

看房预约；具体预约冲突规则由事务服务执行

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| property_id | BIGINT | 否 |  |  |
| prospect_id | BIGINT | 否 |  |  |
| host_staff_id | BIGINT | 是 |  |  |
| starts_at | TIMESTAMP WITH TIME ZONE | 否 |  |  |
| ends_at | TIMESTAMP WITH TIME ZONE | 否 |  |  |
| status | TEXT | 否 | 'requested' | requested / confirmed / completed / cancelled |
| idempotency_key | TEXT | 否 |  |  |

约束与关联：

- FK organization_id, property_id → property_leasing.properties.organization_id, property_leasing.properties.id
- UNIQUE organization_id, idempotency_key
- CHECK `ends_at > starts_at`
- FK organization_id, prospect_id → property_leasing.parties.organization_id, property_leasing.parties.id
- UNIQUE organization_id, id
- CHECK `status IN ('requested','confirmed','completed','cancelled')`
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键
- 跨服务逻辑引用 host_staff_id → identity_access.staff.id；由 API / 事件校验，非数据库外键

## property_leasing.lease_tenants

一份租约的多位租客

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| lease_id | BIGINT | 否 |  |  |
| party_id | BIGINT | 否 |  |  |

约束与关联：

- UNIQUE organization_id, lease_id, party_id
- FK organization_id, lease_id → property_leasing.leases.organization_id, property_leasing.leases.id
- FK organization_id, party_id → property_leasing.parties.organization_id, property_leasing.parties.id
- UNIQUE organization_id, id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## property_leasing.rent_invoices

应收租金；逾期由到期日与实收余额计算

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| lease_id | BIGINT | 否 |  |  |
| reference | TEXT | 否 |  |  |
| due_on | DATE | 否 |  |  |
| period_start | DATE | 否 |  |  |
| period_end | DATE | 否 |  |  |
| amount | NUMERIC(14, 2) | 否 |  |  |
| currency | TEXT | 否 | 'AUD' |  |
| status | TEXT | 否 | 'issued' | issued / void |

约束与关联：

- CHECK `period_end >= period_start`
- FK organization_id, lease_id → property_leasing.leases.organization_id, property_leasing.leases.id
- UNIQUE organization_id, id
- CHECK `amount >= 0`
- UNIQUE organization_id, reference
- CHECK `status IN ('issued','void')`
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## property_leasing.payment_allocations

收款核销到账单；跨行余额和币种由事务服务校验

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| payment_id | BIGINT | 否 |  |  |
| invoice_id | BIGINT | 否 |  |  |
| amount | NUMERIC(14, 2) | 否 |  |  |

约束与关联：

- UNIQUE organization_id, id
- FK organization_id, payment_id → property_leasing.payments.organization_id, property_leasing.payments.id
- UNIQUE organization_id, payment_id, invoice_id
- FK organization_id, invoice_id → property_leasing.rent_invoices.organization_id, property_leasing.rent_invoices.id
- CHECK `amount > 0`
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## maintenance.maintenance_drafts

维修草稿内容；可持久化模拟内容但不得宣称写入业务系统

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| task_id | BIGINT | 否 |  |  |
| property_id | BIGINT | 否 |  |  |
| created_by | BIGINT | 否 |  |  |
| summary | TEXT | 否 |  |  |
| priority | TEXT | 否 | 'medium' | low / medium / high / urgent |
| mode | TEXT | 否 | 'mock' | mock / live |
| status | TEXT | 否 | 'simulated' | simulated / draft / submitted / discarded |
| idempotency_key | TEXT | 否 |  |  |

约束与关联：

- CHECK `status IN ('simulated','draft','submitted','discarded')`
- UNIQUE organization_id, idempotency_key
- CHECK `priority IN ('low','medium','high','urgent')`
- CHECK `mode != 'mock' OR status IN ('simulated','discarded')`
- CHECK `mode IN ('mock','live')`
- UNIQUE organization_id, id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键
- 跨服务逻辑引用 task_id → staff_agent.staff_tasks.id；由 API / 事件校验，非数据库外键
- 跨服务逻辑引用 property_id → property_leasing.properties.id；由 API / 事件校验，非数据库外键
- 跨服务逻辑引用 created_by → identity_access.staff.id；由 API / 事件校验，非数据库外键

## maintenance.maintenance_orders

正式维修工单；不把模拟草稿混入本表

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| property_id | BIGINT | 否 |  |  |
| reference | TEXT | 否 |  |  |
| summary | TEXT | 否 |  |  |
| priority | TEXT | 否 | 'medium' | low / medium / high / urgent |
| status | TEXT | 否 | 'open' | open / in_progress / completed / cancelled |
| reported_by_party_id | BIGINT | 是 |  |  |
| assigned_staff_id | BIGINT | 是 |  |  |
| vendor_id | BIGINT | 是 |  |  |
| version | INTEGER | 否 | 1 |  |

约束与关联：

- UNIQUE organization_id, reference
- CHECK `status IN ('open','in_progress','completed','cancelled')`
- CHECK `priority IN ('low','medium','high','urgent')`
- UNIQUE organization_id, id
- CHECK `version > 0`
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键
- 跨服务逻辑引用 property_id → property_leasing.properties.id；由 API / 事件校验，非数据库外键
- 跨服务逻辑引用 reported_by_party_id → property_leasing.parties.id；由 API / 事件校验，非数据库外键
- 跨服务逻辑引用 assigned_staff_id → identity_access.staff.id；由 API / 事件校验，非数据库外键
- 跨服务逻辑引用 vendor_id → property_leasing.parties.id；由 API / 事件校验，非数据库外键

## maintenance.approval_requests

未来真实操作审批；审批通过不等于执行成功

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| draft_id | BIGINT | 否 |  |  |
| requested_by | BIGINT | 否 |  |  |
| reviewer_id | BIGINT | 是 |  |  |
| status | TEXT | 否 | 'pending' | pending / approved / rejected / cancelled |
| decision_at | TIMESTAMP WITH TIME ZONE | 是 |  |  |
| decision_note | TEXT | 是 |  |  |

约束与关联：

- UNIQUE organization_id, id
- CHECK `status IN ('pending','approved','rejected','cancelled')`
- CHECK `status NOT IN ('approved','rejected') OR (reviewer_id IS NOT NULL AND decision_at IS NOT NULL)`
- FK organization_id, draft_id → maintenance.maintenance_drafts.organization_id, maintenance.maintenance_drafts.id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键
- 跨服务逻辑引用 requested_by → identity_access.staff.id；由 API / 事件校验，非数据库外键
- 跨服务逻辑引用 reviewer_id → identity_access.staff.id；由 API / 事件校验，非数据库外键

## maintenance.maintenance_events

工单状态变更与处理历史

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| order_id | BIGINT | 否 |  |  |
| actor_staff_id | BIGINT | 否 |  |  |
| event_type | TEXT | 否 |  |  |
| details | JSONB | 否 | '{}'::jsonb |  |

约束与关联：

- UNIQUE organization_id, id
- FK organization_id, order_id → maintenance.maintenance_orders.organization_id, maintenance.maintenance_orders.id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键
- 跨服务逻辑引用 actor_staff_id → identity_access.staff.id；由 API / 事件校验，非数据库外键

## inspection_report.inspections

人工检查或入住退租检查

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| property_id | BIGINT | 否 |  |  |
| inspector_id | BIGINT | 是 |  |  |
| kind | TEXT | 否 |  | routine / move_in / move_out / video |
| inspected_at | TIMESTAMP WITH TIME ZONE | 否 |  |  |
| status | TEXT | 否 | 'scheduled' | scheduled / completed / cancelled |
| summary | TEXT | 否 | '' |  |

约束与关联：

- CHECK `status IN ('scheduled','completed','cancelled')`
- CHECK `kind IN ('routine','move_in','move_out','video')`
- UNIQUE organization_id, id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键
- 跨服务逻辑引用 property_id → property_leasing.properties.id；由 API / 事件校验，非数据库外键
- 跨服务逻辑引用 inspector_id → identity_access.staff.id；由 API / 事件校验，非数据库外键

## inspection_report.inspection_findings

检查发现；证据通过 inspection_reports 关联现有报告与文件

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| inspection_id | BIGINT | 否 |  |  |
| area | TEXT | 否 |  |  |
| description | TEXT | 否 |  |  |
| severity | TEXT | 否 |  | info / low / medium / high / critical |
| evidence | JSONB | 否 | '[]'::jsonb |  |

约束与关联：

- UNIQUE organization_id, id
- FK organization_id, inspection_id → inspection_report.inspections.organization_id, inspection_report.inspections.id
- CHECK `severity IN ('info','low','medium','high','critical')`
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## inspection_report.inspection_reports

检查与现有 public.reports 桥接；不复制报告 JSON 或媒体

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| inspection_id | BIGINT | 否 |  |  |
| report_id | BIGINT | 否 |  |  |

约束与关联：

- UNIQUE organization_id, inspection_id, report_id
- UNIQUE organization_id, id
- FK organization_id, inspection_id → inspection_report.inspections.organization_id, inspection_report.inspections.id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## inspection_report.report_jobs

现有视频分析图的未来持久化运行；不代表已接入 worker/checkpoint

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| requested_by_user_id | BIGINT | 否 |  |  |
| input_file_id | BIGINT | 否 |  |  |
| report_id | BIGINT | 是 |  |  |
| inspection_id | BIGINT | 是 |  |  |
| status | TEXT | 否 | 'queued' | queued / running / completed / failed / cancelled |
| validation_passed | BOOLEAN | 是 |  |  |
| idempotency_key | TEXT | 否 |  |  |
| pipeline_version | TEXT | 否 |  |  |
| finished_at | TIMESTAMP WITH TIME ZONE | 是 |  |  |

约束与关联：

- UNIQUE organization_id, id
- FK organization_id, inspection_id → inspection_report.inspections.organization_id, inspection_report.inspections.id
- UNIQUE organization_id, requested_by_user_id, idempotency_key
- CHECK `status IN ('queued','running','completed','failed','cancelled')`
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## inspection_report.report_job_steps

视频抽帧、检测、报告生成等阶段运行指标；不存原始图像字节或隐藏思维链

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| job_id | BIGINT | 否 |  |  |
| step_name | TEXT | 否 |  |  |
| attempt | INTEGER | 否 |  |  |
| status | TEXT | 否 |  | running / completed / failed / skipped |
| metrics | JSONB | 否 | '{}'::jsonb |  |
| error_code | TEXT | 是 |  |  |

约束与关联：

- UNIQUE organization_id, job_id, step_name, attempt
- CHECK `attempt > 0`
- FK organization_id, job_id → inspection_report.report_jobs.organization_id, inspection_report.report_jobs.id
- UNIQUE organization_id, id
- CHECK `status IN ('running','completed','failed','skipped')`
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## knowledge.knowledge_bases

知识库与外部检索服务定位；向量存储可后接

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| code | TEXT | 否 |  |  |
| name | TEXT | 否 |  |  |
| audience | TEXT | 否 | 'staff' | staff / tenant / public |
| retrieval_provider | TEXT | 否 |  |  |
| external_dataset_id | TEXT | 是 |  |  |

约束与关联：

- UNIQUE organization_id, code
- CHECK `audience IN ('staff','tenant','public')`
- UNIQUE organization_id, id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## knowledge.knowledge_documents

知识文档版本和来源；正文文件复用 public.files

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| knowledge_base_id | BIGINT | 否 |  |  |
| document_key | TEXT | 否 |  |  |
| version | INTEGER | 否 |  |  |
| title | TEXT | 否 |  |  |
| file_id | BIGINT | 是 |  |  |
| external_document_id | TEXT | 是 |  |  |
| status | TEXT | 否 | 'draft' | draft / published / retired |

约束与关联：

- CHECK `status IN ('draft','published','retired')`
- UNIQUE organization_id, id
- FK organization_id, knowledge_base_id → knowledge.knowledge_bases.organization_id, knowledge.knowledge_bases.id
- CHECK `version > 0`
- UNIQUE organization_id, knowledge_base_id, document_key, version
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## knowledge.knowledge_role_access

知识库访问角色；员工必须在调用检索前通过检查

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| knowledge_base_id | BIGINT | 否 |  |  |
| role_id | BIGINT | 否 |  |  |

约束与关联：

- FK organization_id, knowledge_base_id → knowledge.knowledge_bases.organization_id, knowledge.knowledge_bases.id
- UNIQUE organization_id, id
- UNIQUE organization_id, knowledge_base_id, role_id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键
- 跨服务逻辑引用 role_id → identity_access.roles.id；由 API / 事件校验，非数据库外键

## staff_agent.agent_definitions

版本化 Agent 注册；A2A 只是可选适配器，密钥不入本表

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| code | TEXT | 否 |  |  |
| version | TEXT | 否 |  |  |
| transport | TEXT | 否 | 'local' | local / a2a |
| endpoint | TEXT | 是 |  |  |
| credential_ref | TEXT | 是 |  |  |
| capabilities | JSONB | 否 | '[]'::jsonb |  |
| enabled | BOOLEAN | 否 | false |  |

约束与关联：

- CHECK `transport != 'a2a' OR endpoint IS NOT NULL`
- UNIQUE organization_id, id
- UNIQUE organization_id, code, version
- CHECK `transport IN ('local','a2a')`
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## staff_agent.outbox_events

事务内写入待发送事件；dispatcher 未来实现，交付按至少一次设计

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| event_key | TEXT | 否 |  |  |
| event_type | TEXT | 否 |  |  |
| aggregate_type | TEXT | 否 |  |  |
| aggregate_id | BIGINT | 否 |  |  |
| payload | JSONB | 否 |  |  |
| status | TEXT | 否 | 'pending' | pending / delivered / failed |
| attempts | INTEGER | 否 | 0 |  |
| available_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| delivered_at | TIMESTAMP WITH TIME ZONE | 是 |  |  |

约束与关联：

- CHECK `attempts >= 0`
- UNIQUE organization_id, id
- CHECK `status IN ('pending','delivered','failed')`
- UNIQUE organization_id, event_key
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## staff_agent.staff_sessions

员工会话；与当前消费者聊天表分离

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| staff_id | BIGINT | 否 |  |  |
| title | TEXT | 否 | '' |  |
| status | TEXT | 否 | 'active' | active / archived |

约束与关联：

- UNIQUE organization_id, id
- CHECK `status IN ('active','archived')`
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键
- 跨服务逻辑引用 staff_id → identity_access.staff.id；由 API / 事件校验，非数据库外键

## staff_agent.prompt_versions

员工意图拆分提示词的不可变版本；路由策略单独版本化

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| agent_id | BIGINT | 否 |  |  |
| version | TEXT | 否 |  |  |
| content | TEXT | 否 |  |  |
| sha256 | TEXT | 否 |  |  |

约束与关联：

- UNIQUE organization_id, agent_id, version
- UNIQUE organization_id, id
- FK organization_id, agent_id → staff_agent.agent_definitions.organization_id, staff_agent.agent_definitions.id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## staff_agent.staff_requests

完整原始请求及最终路由；idempotency_key 由调用端传入并绑定员工

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| session_id | BIGINT | 否 |  |  |
| original_text | TEXT | 否 |  |  |
| idempotency_key | TEXT | 否 |  |  |
| route | TEXT | 否 | 'pending' | pending / execute / human / clarify |
| status | TEXT | 否 | 'received' | received / planned / running / completed / partial / failed / needs_input / needs_review |
| policy_version | TEXT | 否 | 'staff-v2' |  |
| route_reason | TEXT | 是 |  |  |
| final_answer | TEXT | 是 |  |  |
| updated_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |

约束与关联：

- CHECK `route IN ('pending','execute','human','clarify')`
- UNIQUE organization_id, session_id, idempotency_key
- CHECK `status IN ('received','planned','running','completed','partial','failed','needs_input','needs_review')`
- FK organization_id, session_id → staff_agent.staff_sessions.organization_id, staff_agent.staff_sessions.id
- UNIQUE organization_id, id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## staff_agent.audit_events

审计元数据；生产服务角色应仅允许 INSERT/SELECT

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| actor_staff_id | BIGINT | 是 |  |  |
| request_id | BIGINT | 是 |  |  |
| event_type | TEXT | 否 |  |  |
| resource_type | TEXT | 否 |  |  |
| resource_id | TEXT | 是 |  |  |
| details_redacted | JSONB | 否 | '{}'::jsonb |  |

约束与关联：

- FK organization_id, request_id → staff_agent.staff_requests.organization_id, staff_agent.staff_requests.id
- UNIQUE organization_id, id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键
- 跨服务逻辑引用 actor_staff_id → identity_access.staff.id；由 API / 事件校验，非数据库外键

## staff_agent.human_cases

人工案件；需要人工与已成功外部提交分开表示

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| request_id | BIGINT | 否 |  |  |
| assigned_staff_id | BIGINT | 是 |  |  |
| reason | TEXT | 否 |  |  |
| status | TEXT | 否 | 'needs_review' | needs_review / queued / in_progress / resolved / cancelled |
| submission_status | TEXT | 否 | 'not_submitted' | not_submitted / pending / submitted / failed |
| external_reference | TEXT | 是 |  |  |
| submitted_at | TIMESTAMP WITH TIME ZONE | 是 |  |  |

约束与关联：

- CHECK `status IN ('needs_review','queued','in_progress','resolved','cancelled')`
- CHECK `submission_status != 'submitted' OR (external_reference IS NOT NULL AND submitted_at IS NOT NULL)`
- UNIQUE organization_id, id
- FK organization_id, request_id → staff_agent.staff_requests.organization_id, staff_agent.staff_requests.id
- UNIQUE organization_id, request_id
- CHECK `submission_status IN ('not_submitted','pending','submitted','failed')`
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键
- 跨服务逻辑引用 assigned_staff_id → identity_access.staff.id；由 API / 事件校验，非数据库外键

## staff_agent.intent_runs

意图模型调用记录；保存模型输出但不把它当成已授权任务

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| request_id | BIGINT | 否 |  |  |
| prompt_id | BIGINT | 否 |  |  |
| model | TEXT | 否 |  |  |
| attempt | INTEGER | 否 |  |  |
| status | TEXT | 否 |  | ok / invalid / error |
| raw_output | JSONB | 是 |  |  |
| validation_errors | JSONB | 否 | '[]'::jsonb |  |
| latency_ms | INTEGER | 是 |  |  |

约束与关联：

- CHECK `attempt > 0`
- FK organization_id, request_id → staff_agent.staff_requests.organization_id, staff_agent.staff_requests.id
- CHECK `status IN ('ok','invalid','error')`
- CHECK `latency_ms IS NULL OR latency_ms >= 0`
- UNIQUE organization_id, id
- FK organization_id, prompt_id → staff_agent.prompt_versions.organization_id, staff_agent.prompt_versions.id
- UNIQUE organization_id, request_id, id
- UNIQUE organization_id, request_id, attempt
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## staff_agent.staff_tasks

只存校验后的任务；无效模型输出留在 intent_runs

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| request_id | BIGINT | 否 |  |  |
| intent_run_id | BIGINT | 否 |  |  |
| task_key | TEXT | 否 |  |  |
| ordinal | INTEGER | 否 |  |  |
| source_text | TEXT | 否 |  |  |
| span_start | INTEGER | 否 |  |  |
| span_end | INTEGER | 否 |  |  |
| intent | TEXT | 否 |  | knowledge_question / record_query / action_request / unclear |
| business_domain | TEXT | 否 |  |  |
| condition_text | TEXT | 否 | '' |  |
| status | TEXT | 否 | 'pending' | pending / running / ok / denied / unsupported / needs_input / needs_review / failed / skipped |
| parameters | JSONB | 否 | '{}'::jsonb |  |

约束与关联：

- UNIQUE organization_id, request_id, ordinal
- CHECK `span_start >= 0`
- FK organization_id, request_id → staff_agent.staff_requests.organization_id, staff_agent.staff_requests.id
- CHECK `intent IN ('knowledge_question','record_query','action_request','unclear')`
- UNIQUE organization_id, id
- UNIQUE organization_id, request_id, id
- CHECK `span_end > span_start`
- FK organization_id, intent_run_id → staff_agent.intent_runs.organization_id, staff_agent.intent_runs.id
- CHECK `status IN ('pending','running','ok','denied','unsupported','needs_input','needs_review','failed','skipped')`
- UNIQUE organization_id, request_id, task_key
- CHECK `ordinal > 0`
- FK organization_id, request_id, intent_run_id → staff_agent.intent_runs.organization_id, staff_agent.intent_runs.request_id, staff_agent.intent_runs.id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## staff_agent.task_dependencies

保留任务依赖图；staff-v2 策略不自动执行有依赖的请求

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| request_id | BIGINT | 否 |  |  |
| task_id | BIGINT | 否 |  |  |
| depends_on_id | BIGINT | 否 |  |  |

约束与关联：

- UNIQUE organization_id, id
- CHECK `task_id != depends_on_id`
- FK organization_id, request_id, task_id → staff_agent.staff_tasks.organization_id, staff_agent.staff_tasks.request_id, staff_agent.staff_tasks.id
- FK organization_id, request_id, depends_on_id → staff_agent.staff_tasks.organization_id, staff_agent.staff_tasks.request_id, staff_agent.staff_tasks.id
- UNIQUE organization_id, task_id, depends_on_id
- FK organization_id, request_id → staff_agent.staff_requests.organization_id, staff_agent.staff_requests.id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## staff_agent.task_runs

执行尝试；worker 租约用于未来恢复，单有表不代表已经实现队列

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| task_id | BIGINT | 否 |  |  |
| agent_id | BIGINT | 是 |  |  |
| attempt | INTEGER | 否 |  |  |
| status | TEXT | 否 |  | running / ok / denied / unsupported / needs_input / failed / cancelled |
| started_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| finished_at | TIMESTAMP WITH TIME ZONE | 是 |  |  |
| lease_until | TIMESTAMP WITH TIME ZONE | 是 |  |  |
| worker_id | TEXT | 是 |  |  |
| error_code | TEXT | 是 |  |  |

约束与关联：

- FK organization_id, task_id → staff_agent.staff_tasks.organization_id, staff_agent.staff_tasks.id
- UNIQUE organization_id, task_id, attempt
- CHECK `finished_at IS NULL OR finished_at >= started_at`
- CHECK `status IN ('running','ok','denied','unsupported','needs_input','failed','cancelled')`
- FK organization_id, agent_id → staff_agent.agent_definitions.organization_id, staff_agent.agent_definitions.id
- CHECK `attempt > 0`
- UNIQUE organization_id, id
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## staff_agent.a2a_delegations

未来远端任务映射；暂不启动网络通信

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| run_id | BIGINT | 否 |  |  |
| agent_id | BIGINT | 否 |  |  |
| remote_task_id | TEXT | 是 |  |  |
| remote_context_id | TEXT | 是 |  |  |
| protocol_version | TEXT | 否 |  |  |
| idempotency_key | TEXT | 否 |  |  |
| status | TEXT | 否 | 'pending' | pending / working / input_required / completed / failed / cancelled / unknown |
| last_event_id | TEXT | 是 |  |  |
| artifacts | JSONB | 否 | '[]'::jsonb |  |

约束与关联：

- UNIQUE organization_id, idempotency_key
- FK organization_id, run_id → staff_agent.task_runs.organization_id, staff_agent.task_runs.id
- UNIQUE organization_id, id
- FK organization_id, agent_id → staff_agent.agent_definitions.organization_id, staff_agent.agent_definitions.id
- UNIQUE organization_id, agent_id, remote_task_id
- CHECK `status IN ('pending','working','input_required','completed','failed','cancelled','unknown')`
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## staff_agent.task_results

每个执行尝试的结构化结果；状态不从自然语言回答反推

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| run_id | BIGINT | 否 |  |  |
| answer | TEXT | 否 |  |  |
| data | JSONB | 否 | '{}'::jsonb |  |
| source | TEXT | 否 |  | mock / business / knowledge |
| business_persisted | BOOLEAN | 否 | false |  |
| approval_submitted | BOOLEAN | 否 | false |  |

约束与关联：

- UNIQUE organization_id, id
- FK organization_id, run_id → staff_agent.task_runs.organization_id, staff_agent.task_runs.id
- CHECK `source != 'mock' OR (NOT business_persisted AND NOT approval_submitted)`
- UNIQUE organization_id, run_id
- CHECK `source IN ('mock','business','knowledge')`
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

## staff_agent.tool_calls

工具调用轨迹；输入脱敏，授权由工具服务重验

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|---|---|---|---|---|
| id | BIGINT | 否 |  |  |
| created_at | TIMESTAMP WITH TIME ZONE | 否 | CURRENT_TIMESTAMP |  |
| organization_id | BIGINT | 否 |  |  |
| run_id | BIGINT | 否 |  |  |
| call_key | TEXT | 否 |  |  |
| tool_name | TEXT | 否 |  |  |
| effect | TEXT | 否 |  | read / draft / write |
| authorization_decision | TEXT | 否 |  | allow / deny |
| status | TEXT | 否 |  | started / ok / failed / denied |
| arguments_redacted | JSONB | 否 | '{}'::jsonb |  |
| result_summary | JSONB | 否 | '{}'::jsonb |  |
| duration_ms | INTEGER | 是 |  |  |

约束与关联：

- CHECK `effect IN ('read','draft','write')`
- CHECK `authorization_decision != 'deny' OR status = 'denied'`
- FK organization_id, run_id → staff_agent.task_runs.organization_id, staff_agent.task_runs.id
- UNIQUE organization_id, id
- CHECK `authorization_decision IN ('allow','deny')`
- CHECK `duration_ms IS NULL OR duration_ms >= 0`
- UNIQUE organization_id, run_id, call_key
- CHECK `status IN ('started','ok','failed','denied')`
- 跨服务逻辑引用 organization_id → identity_access.organizations.id；由 API / 事件校验，非数据库外键

