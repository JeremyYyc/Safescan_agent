# 按城市分配员工与房源

每个普通员工只有一个 `city_id`，同城允许多名员工。城市只决定员工是否有资格接管资源；
Property Manager 仍须具备有效 building/property scope，不能因此访问同城全部房源。
Manager Admin 保留公司级权限，但为别人分派工作时，目标员工必须与房源同城。

## 数据与服务边界

- `identity_access.cities`：城市编码、名称、州；`staff.city_id` 是本 schema 的外键。
- `property_leasing.buildings.city_id`：城市编码引用，没有跨服务物理外键。
- `properties.city_id`：有大楼时由数据库 trigger 继承；大楼改城同步所有房源，并拒绝冲突城市。
  独立房源直接指定城市。未知城市不允许自动分配。
- 保留 `staff_building_scopes`、`staff_property_scopes`；同城检查叠加具体授权。
- `0015` 追加到 `20261031_0014`，保留 inspection history 的租约关联和 provenance。
  migration 只添加结构、城市参考目录和一致性触发器，不自动修改既有业务数据；城市及员工
  分配数据必须通过手动同步命令预演后显式应用。

旧数据可以暂时缺城市，但新员工创建 API 要求普通员工提供有效城市；未设置城市的员工无法
获得业务资源访问。身份字段由 Identity 维护，领域服务通过实时 SubjectProjection 校验城市、
在职状态和 staff public ID，不信任旧 token 中的城市。

## 分配入口

- 潜客联系房源：从同城 active Leasing Consultant 池稳定选择，选择后再次校验。
- 案件人工改派：即使管理员操作，也拒绝跨城市目标员工。
- 维修分派：校验 active Maintainer 城市；列表、详情、状态推进、工作上下文和报告上下文都
  检查当前城市，防止旧工单授权继续生效。
- domain seed：通过 Identity 的同城 active staff 目录选择 Property Manager，取消员工列表
  顺序与大楼顺序的绑定。无同城人员时保持待分配。
- 批量导入：`scripts/data/integrate_execution_dataset.py` 使用源城市，不再全局哈希或轮询员工。
  缺少同城员工时保留业务记录和待分配状态；已结束记录保留历史处理人。

`normalize_city` 仅将此批源数据里误填为 city 的 suburb 规范成城市，没有建立片区管理层级。
例如 NSW Box Hill 与 VIC Box Hill 分别归 Sydney、Melbourne；不能仅凭州猜测城市。

## API

- `GET /api/v1/iam/cities`：城市目录，要求 `iam:staff:read`。
- `POST /api/v1/iam/staff`：普通员工需要 `city_id`。
- `PATCH /api/v1/iam/staff/{staff_id}/city`：`city_id`、`reason`、`version`，要求
  `iam:staff:employment_manage`；检查版本、记录审计、递增 auth version 并撤销旧会话。
- `GET /internal/v1/staff-directory?role=property_manager`：服务认证的最小员工目录。
- 员工资料、SubjectProjection、分配候选和房源投影增加 `city_id`。

调城先使旧城访问失效，随后运行交接修正脚本；脚本结束旧 scopes，并交接未完成案件和工单。
原始租约、账单、已完成检查和已结束工单不改写。员工需要重新登录。

## 现有数据修正

先备份，再执行 Alembic `upgrade head`。在已安装共享包的 Python 环境中运行：

```sh
python scripts/data/reconcile_city_assignments.py --dataset /path/to/dataset --report /tmp/city-preview.json
python scripts/data/reconcile_city_assignments.py --dataset /path/to/dataset --apply --report /tmp/city-applied.json
```

连接从 `DATABASE_URL` 读取。默认仅预演并回滚；`--apply` 在一个事务内提交。脚本使用事务锁和
表写锁，保留交接审计，允许幂等重跑。未识别城市进入待分配，冲突大楼城市会终止整个事务。
既有城市不被默认 seed 映射覆盖。非 demo 员工先通过管理 API 配置城市。

本次默认人员安排：LC/PM 001→Sydney、002→Melbourne、003→Brisbane、004→Adelaide；
MT001→Sydney、MT002→Brisbane、MT003→Melbourne。可在同城继续增加员工。

2026-10-31 本地应用结果见 `database/city-assignment-report-20261031.json`：
508 套房源归入 Sydney 114、Melbourne 150、Brisbane 130、Adelaide 80、Perth 34；
Perth 的 9 栋大楼缺 Property Manager，Adelaide/Perth 缺 Maintainer，因此保留待分配。
旧授权结束 123 条，新增大楼授权 118 条，交接未完成案件 1 条、工单 143 条。

## 验证与回滚

- 空库完整 upgrade、城市 migration downgrade/upgrade；已部署旧库升级不重写旧 revision。
- PostgreSQL 测试覆盖跨城拒绝、同城多人但授权独立、实时调城、继承触发器、案件与工单分派。
- 完整数据副本验证重复修正零变更、有效授权零跨城、房源数量不变。
- 本地真实 Gateway 验证：`python scripts/ci/city-assignment-smoke.py http://127.0.0.1:8080`。
- 对照备份，1880 份租约及其租客/文档、6783 条检查、3616 条发现和已结束工单保持原样。
- 前端执行 `npm run staff:check`，共享 schema 和服务契约/集成测试分别执行。

DDL downgrade 只撤销城市结构，不逆转已交接的业务分配；完整数据回滚应使用应用前备份。
本地备份保存在 `/private/tmp/safescan-before-city-20261031.dump`。城市部署基于当前运行镜像叠加
改动并三方合并，保留已有媒体、检查历史和分页功能；原镜像有 `safescan-city-base-*` 回滚标签。
新数据集功能来自另一个工作树，后续从源代码统一重建时，应先合并那部分既有功能与本次城市变更。

## 2026-11-02 按城市补齐员工

在既有 12 名员工基础上新增 4 人，总计 16 人。每个有房源的城市至少有一名 Leasing Consultant、
Property Manager 和 Maintainer；人员需要增加时继续顺延岗位编号，不改变既有员工账号或密码。

| 员工编号 | 姓名 | 岗位 | 城市 | 邮箱 |
|---|---|---|---|---|
| LC005 | Lucas Anderson | Leasing Consultant | Perth | LucasSafescan@outlook.com |
| PM005 | Isabella Brooks | Property Manager | Perth | IsabellaSafescan@outlook.com |
| MT004 | Mason Lewis | Maintainer | Adelaide | MasonSafescan@outlook.com |
| MT005 | Benjamin Scott | Maintainer | Perth | BenjaminSafescan@outlook.com |

统一沿用 `岗位前缀 + 三位编号`、`FirstNameLastName` username、
`{FirstName}Safescan@outlook.com` 邮箱和 `staff{username}123456` 初始密码规则。
使用同一个非生产 Identity seed，密码仍按 Argon2id 写库，账号及 employment 直接为 active。
重复运行只补缺失账号，不重置原账号；生产环境仍禁止 demo seed。

补员后重新执行同城分配：PM005 接管 Perth 的 9 栋大楼/34 套房源，MT004/MT005
分别接管 Adelaide 29 张、Perth 12 张待分配工单。已结束业务记录保留。
执行结果见 `database/city-staff-report-20261102.json`。
本次操作前备份：`/private/tmp/safescan-before-city-staff-20261102.dump`。

## 2026-11-02 显式修正历史租赁订单归属

此前默认城市同步仅交接未关闭案件，不改已完成案件。本次经明确授权，单独运行
`scripts/data/reassign_historical_leasing_orders.py`：按房源已有城市，把关联租约的跨城案件
分配给 active 同城 Leasing Consultant。保留合法同城分配；同城多人时优先沿用房源顾问，
否则按房源 public ID 稳定选择。缺少城市或同城顾问时整批拒绝，不跨城兜底。

默认只预览；应用必须显式指定 `--apply --expected-changes <预览数量>`。脚本事务内锁定相关表，
仅变更案件及联系线程的负责人和版本/更新时间，每次变更追加包含原负责人、新负责人、
城市、房源及 operation ID 的 `consultant_reassigned` 审计事件。不会修改案件原阶段、关闭时间、
租约状态、租金、合同条款、文档摘要、创建人、签署事件或签署时间；提交前再次核验保护字段指纹。
该脚本不加入部署、默认 seed 或通用城市同步流程。

本次先在完整备份副本中验证，再修正 1398 个案件；重复执行零变更。
调整后 LC001/Sydney 427、LC002/Melbourne 550、LC003/Brisbane 487、LC004/Adelaide 292、
LC005/Perth 124，共 1880 份租约，跨城归属为 0。
结果与保护字段指纹见 `docs/backend/handover/historical-leasing-city-assignment-20261102.json`。
本次操作前完整数据库备份为 `/private/tmp/safescan-before-historical-leasing-20261102-f786.dump`。
