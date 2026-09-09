# 目标仓库与服务目录

## 设计依据

APLP 将独立后端放在 `services/<service>`，公共 Python 能力放在 `packages`，数据库和基础设施
独立管理，每个服务拥有自己的 Dockerfile、依赖和测试。SafeScan 现有代码已经集中在 `backend`
下，因此采用同一思想但保留 `backend` 作为后端聚合根，减少迁移期路径震荡。

## 目标层级

```text
Safescan_agent/
├── .github/workflows/              # CI、镜像和集成验证
├── backend/
│   ├── services/
│   │   ├── staff-portal-api/
│   │   ├── tenant-portal-api/
│   │   ├── identity-access-service/
│   │   ├── property-leasing-service/
│   │   ├── maintenance-service/
│   │   ├── inspection-report-service/
│   │   ├── knowledge-service/
│   │   └── staff-agent-service/
│   ├── packages/
│   │   └── safescan-common/         # 小而稳定的公共技术包
│   ├── alembic/                     # 迁移期统一迁移入口
│   ├── tests/                       # 迁移期回归、契约和端到端测试
│   ├── app/                         # 当前单体基线，逐服务迁出
│   └── Dockerfile                   # 当前统一运行镜像
├── database/                        # 目标：schema 初始化、seed、迁移说明
├── docs/
│   ├── backend/                     # 后端架构、服务、数据、API、运维、交接
│   └── diagrams/                    # 可导出的架构和 ER 图
├── frontend/
│   ├── apps/
│   │   ├── staff-web/              # 新员工 React Portal
│   │   └── tenant-web/             # 新客户 React Portal
│   ├── packages/                   # 无业务状态的 UI/生成工具
│   └── src/ ...                    # 现有报告前端；迁移完成前作为受保护旧基线
├── gateway/
└── docker-compose*.yml
```

## 单个服务的标准结构

```text
<service>/
├── app/
│   ├── main.py                      # 进程装配和生命周期
│   ├── controllers/                 # FastAPI router、HTTP 映射
│   ├── schemas/                     # 请求和响应 DTO
│   ├── services/                    # 用例与事务边界
│   ├── mappers/                     # ORM 查询、持久化和领域对象映射
│   ├── models/                      # 服务自有 SQLAlchemy 模型
│   ├── domain/                      # 领域值对象、规则和异常
│   ├── clients/                     # 其他服务的显式客户端
│   ├── events/                      # inbox/outbox 事件契约与处理器
│   ├── workers/                     # 同一服务边界内的异步入口
│   └── core/                        # 本服务配置、DB、依赖注入
├── migrations/                      # 服务完成拆分后拥有自己的 schema 迁移
├── tests/
│   ├── unit/
│   ├── integration/
│   └── contract/
├── Dockerfile
├── requirements.txt
└── README.md
```

## 迁移规则

1. `backend/app` 是迁移前基线，不与新目录双写。
2. 每次只迁移一个完整用例链：Controller、Schema、Service、Mapper、Model 和测试一起移动。
3. 一个数据库表只有一个服务拥有写权限；跨服务只通过 API 或事件访问。
4. 首期六个 schema 可以继续位于同一 PostgreSQL 实例，但连接账户最终按 schema 最小授权拆分。
5. 服务拆分后拥有独立镜像和健康检查；Compose 中不再共享一个 `backend` 镜像标签。
6. 公共包只收录横切技术能力，禁止放业务模型、业务状态枚举或跨服务 ORM。
7. Compose 默认 profile 只包含非 Agent P0 主链路；Knowledge/Qdrant 使用 `future` profile，Agent
   使用 `agent` profile，关闭可选 profile 时不得影响核心服务 readiness。

## 命名约定

- 部署单元和目录使用 kebab-case：`identity-access-service`。
- Python 包使用 snake_case：`identity_access`。
- Controller 文件按资源命名：`users_controller.py`。
- Service 文件按用例或聚合命名：`auth_service.py`。
- Mapper 文件按聚合命名：`user_mapper.py`。
- 数据库 schema 使用 snake_case，并与数据所有者一致。
