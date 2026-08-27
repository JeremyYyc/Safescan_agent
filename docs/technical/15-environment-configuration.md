# Docker 统一环境配置技术文档

## 1. 目标

SafeScan 以 Docker Compose 作为开发、测试和生产部署边界。环境变量的唯一配置入口为仓库根目录下按环境命名的 Compose env 文件；服务不再分别维护 `backend/.env`、`frontend/.env` 和 `backend/.env.production`。

```text
.env.example       -> 配置模板，不含密钥
.env               -> 本地开发，禁止提交
.env.test          -> 集成测试，禁止提交
.env.staging       -> 灰度环境，由部署系统注入
.env.production    -> 生产环境，由 Secret Manager/部署系统注入
```

根目录 env 文件同时承担两种职责：Compose 的 `${VAR}` 插值来源，以及通过 `env_file` 注入 backend 的运行时环境。前端的 `VITE_API_BASE` 是构建期参数，由 Compose 传给 frontend build args；不要把服务端密钥传给 frontend。

迁移完成后，仓库根目录的 `.env` 和 `.env.production` 是本地/生产实际文件；`.env.test` 为可提交的安全测试配置，生产密钥仍必须由部署系统注入。`.env.example` 是字段模板。

## 2. 文件规则

| 文件 | 用途 | 是否提交 |
|---|---|---:|
| `.env.example` | 所有变量和安全默认值的模板 | 是 |
| `.env` | 本地 Docker Compose | 否 |
| `.env.test` | 测试数据库和 mock 配置 | 否 |
| `.env.staging` | staging 灰度配置 | 否 |
| `.env.production` | 生产配置 | 否 |

敏感变量不得写入 Dockerfile、镜像层、Compose 文件、README 或日志。生产环境优先通过 CI/CD secret、Secret Manager 或部署平台 secret 生成 `.env.production`，而不是人工提交文件。

## 3. 变量分组

### 3.1 应用与模型

```env
QWEN_API_KEY=
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL_FAST=qwen3.7-flash
QWEN_MODEL_STANDARD=qwen3.7-plus-2026-05-26
QWEN_MODEL_REASONING=qwen3.8-max
QWEN_MODEL_VISION=qwen3.7-plus-2026-05-26
QWEN_MODEL_OCR=qwen3.5-ocr
QWEN_EMBEDDING_MODEL=text-embedding-v4
QWEN_EMBEDDING_DIMENSION=1024
QWEN_RERANK_MODEL=qwen3-rerank
AGENT_MAX_CONCURRENCY=5
```

兼容期可读取 `DASHSCOPE_API_KEY` 和 `ALIBABA_MODEL_L1/L2/L3/VL`，但新配置统一使用 `QWEN_*`。生产模型不得使用 `latest` 标签。

### 3.2 数据库与存储

```env
MYSQL_DATABASE=safescan_agent
MYSQL_ROOT_PASSWORD=
DATABASE_URL=mysql+pymysql://root:<password>@db:3306/safescan_agent?charset=utf8mb4
OUTPUT_DIR=/app/uploads
```

Compose 网络中 backend 访问数据库必须使用服务名 `db`，不能使用 `127.0.0.1`。P00 完成 PostgreSQL 迁移后，统一替换为 PostgreSQL URL，并增加 `PGVECTOR_ENABLED`、数据库用户和密码变量；不要在同一环境同时维护两个事实源。

### 3.3 安全与前端

```env
AUTH_SECRET=
AUTH_EXPIRE_HOURS=8
VITE_API_BASE=http://localhost:8000
```

`AUTH_SECRET` 在 test 之外必须是随机高熵值。`VITE_API_BASE` 只允许浏览器需要的公开 API 地址；任何 API key、数据库密码和签名密钥都不能以 `VITE_` 开头。

### 3.4 功能开关

```env
LANGGRAPH_ENABLED=false
RAG_SAFETY_ENABLED=false
REPORT_CITATIONS_ENABLED=false
HITL_ENABLED=false
QWEN_MODEL_CANARY_ENABLED=false
```

每个开关必须有默认值、负责人、启用条件、监控指标和回滚条件。生产不允许通过临时容器内手工修改开关。

## 4. Compose 注入约定

开发 Compose 使用根目录 `.env`：

```bash
docker compose --env-file .env up --build
```

测试使用 `.env.test` 和测试 Compose 文件：

```bash
docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml up --build --abort-on-container-exit
```

生产使用固定的 production 文件：

```bash
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Compose 文件中只放非敏感默认值和服务拓扑。服务运行时变量通过 `env_file` 注入；frontend 只接收 build args。修改 env 后必须重新创建 backend，修改 `VITE_API_BASE` 后必须重新构建 frontend。

## 5. 当前项目迁移要求

1. 将 `backend/.env` 的变量迁移到根目录 `.env`，本地 API 地址由 `VITE_API_BASE` 统一管理。
2. 将 `backend/.env.production` 和 `backend/.env.test` 迁移为根目录 `.env.production`、`.env.test`。
3. Compose 的 backend 统一读取根目录 env 文件。
4. 删除文档中直接运行 backend 时的独立 `.env` 作为部署说明；裸机开发可保留兼容读取，但不是 Docker 生产路径。
5. README 只维护 `.env.example` 字段说明，不再复制多份可能漂移的变量清单。
6. 启动前执行变量校验，缺失 `QWEN_API_KEY`、`DATABASE_URL` 或 `AUTH_SECRET` 时在 production 明确失败。

## 6. 校验与安全检查

发布前必须检查：

```bash
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml config
```

检查输出不得包含真实 API key、数据库密码或 `AUTH_SECRET`。CI 应检查：env 文件是否被提交、production 是否使用默认密码、frontend 构建产物是否包含服务端密钥、backend 是否连接 Compose 服务名。

运行时 `/health/ready` 检查数据库、模型配置和必要的外部依赖；密钥只报告 `configured=true/false`，不得返回密钥值。

## 7. 版本与变更管理

新增或修改变量必须同步更新 `.env.example`、本文档、Compose 配置和部署 Runbook，并说明：类型、是否必填、默认值、作用域、是否敏感、变更是否需要重建镜像。

模型变量还必须记录 model version；Embedding 变量变化必须触发向量索引迁移评审，不能只修改 env 后重启服务。
