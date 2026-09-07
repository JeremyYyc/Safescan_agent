# Safescan 数据库与微服务设计 v1

日期：2026-09-07。状态：**可评审的模拟设计，未接入运行中的 API、Alembic 或真实业务数据库**。

依据当前仓库 PostgreSQL 17 / SQLAlchemy 2 / Alembic / FastAPI / LangGraph / MinIO，以及员工侧 Dify「多任务串行与人工分流 v2」。最近补充的两人协作边界是：本项目负责员工侧 Agent，另一位同学负责租户／潜在租户侧 Agent；两侧共享领域服务，不共享各自的运行数据库。

## 交付物与阅读顺序

1. [微服务架构与团队边界](MICROSERVICES.md)：服务划分、数据所有权、部署阶段和调用方式。
2. [完整数据库设计](DATABASE_DESIGN.md)：现有十表接续、关键关系、事务、约束、权限和迁移。
3. [双方协作接口契约](CONTRACTS.md)：身份、资源过滤、API、事件、错误、租户侧建议表。
4. [字段级数据字典](DATA_DICTIONARY.md)：45 张新增表的字段、可空性、约束与逻辑引用。
5. `schema.py`：唯一新增结构定义；生成 `001_schema.sql` 和 `services/*.sql`。
6. `002_seed.sql`：两个组织、四名员工、房源、租约、账单、维修、检查、申请和看房的合成数据。
7. `intent_agent.py`：可替换 planner 的员工意图识别雏形，默认只用关键词 Mock。
8. `intent_examples.json`：7 个离线意图识别示例。
9. `test_design.py`：离线边界测试；`postgres_checks.sql`：隔离 PostgreSQL 验证脚本。

## 服务与表数

以 `schema.py` / 数据字典为准。新增 45 张表分布于 6 个服务 schema；加上现有 10 张表，设计覆盖 55 张表。租户 Agent 的私有表只提供契约建议，不擅自实现另一位同学的模块。

生产采用每个服务独立数据库／凭据；本地模拟为一库多 schema，便于联调。`001_schema.sql` 是所有服务的合集，`services/*.sql` 是独立部署的同一份定义，**二选一，不重复执行**。

## 离线运行

从仓库根目录：

```sh
backend/.venv/bin/python design/database_v1/schema.py
backend/.venv/bin/python design/database_v1/intent_agent.py
backend/.venv/bin/python -m pytest design/database_v1/test_design.py -q
```

默认原型不连接数据库、不调用模型、不查询业务、不提交人工工单。`route=execute` 仅表示可以进入下一层授权与执行流程，不代表已经获得房源权限或已经执行。

## 隔离数据库模拟

只使用显式指定的空测试库，不读取根 `.env` 自动连接日常数据库：

```sh
psql "$TEST_DATABASE_URL" -v ON_ERROR_STOP=1 -f design/database_v1/001_schema.sql
psql "$TEST_DATABASE_URL" -v ON_ERROR_STOP=1 -f design/database_v1/002_seed.sql
psql "$TEST_DATABASE_URL" -v ON_ERROR_STOP=1 -f design/database_v1/postgres_checks.sql
```

数据验证脚本最终回滚自己创建的测试执行记录，保留初始模拟数据。SQL 无 DROP SCHEMA，无跨服务外键，无账号口令。

`003_existing_links.sql` 仅用于已有 `public.reports` 与新检查表同属报告服务时建立桥接外键，独立空库模拟不执行。其余旧表关联通过服务接口校验。

## 验证与限制

离线测试可以验证意图路由和元数据约束，不能证明数据库已完成安装或权限隔离。PostgreSQL 执行结果见 [VALIDATION.md](VALIDATION.md)。Agent 当前为 Mock，无实际 A2A server/client、worker、事务发件箱 dispatcher、身份服务或 API。

关键词 Mock 有意只覆盖少量演示句式，不能用于开放自然语言生产流量。接入模型后继续执行同一份结构校验、原文覆盖校验和确定性路由，并补充对漏拆、误分类、指代、省略、多语言的评估集。
