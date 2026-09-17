# Safe Scan Agent

家庭安全视频分析 Demo：上传视频 → 内存抽帧/筛选/视觉理解 → 多角色分析 → 完整报告，支持报告问答与按需 PDF。

## 当前技术栈

- 前端：React 19、Vite 7、React Router、DOMPurify。
- 编排：LangGraph 1.2.11；报告、上传、聊天、PDF 及模型工具循环均使用图。
- 后端：FastAPI、Pydantic、OpenAI-compatible Qwen 客户端。
- 数据：PostgreSQL 17、SQLAlchemy 2、psycopg 3、Alembic。
- 文件：私有 MinIO；视频/图片/PDF 使用内存流，无应用侧业务文件落盘。
- 视觉与 PDF：原 YOLOv8m、OpenCV、PyTorch、PyAV、ReportLab。

项目文档统一从 [文档中心](docs/README.md) 进入；后端微服务目标目录、数据所有权和
Controller / Service / Mapper / Model 分层见 [后端文档](docs/backend/README.md)。当前架构、
节点、数据库和路径说明见 [当前技术与路径索引](docs/ARCHITECTURE.zh-CN.md)；代理入口和扩展
方式见 [Nginx 网关](docs/NGINX_GATEWAY.zh-CN.md)；阶段验收见
[执行记录](docs/REFACTOR_EXECUTION.zh-CN.md)。

## 唯一配置

复制根目录 `.env.example` 为根 `.env`，填写 PostgreSQL、MinIO、Qwen 与鉴权密钥。真实 `.env` 已被 Git 和镜像构建排除；不要创建 backend/frontend 或 test/production 环境副本。

- `Settings` 统一读取，优先级：显式覆盖 → 进程环境 → 根 `.env` → 默认值。
- 容器数据库使用 `db:5432`；后端 MinIO 客户端使用 `gateway:9000`，不能绕过网关连接存储网络。数据库 URL 中密码需要 URL 编码。
- `POSTGRES_SERVICE_SCHEMAS` 记录当前固定的六个服务 schema；它们共享一套 PostgreSQL 实例、数据库和连接凭据，不需要六条 `DATABASE_URL`。
- `AUTH_SECRET`、`PUBLIC_ID_SECRET` 使用随机长密钥，不能留空；改变它们会使旧 token/公开 ID 失效。
- 前端固定同源 `/api`，没有 `VITE_API_BASE` 或 CORS 配置；根 env 不向浏览器公开。
- 未启用的历史本地配置仅作为注释留存，不参与运行。

## 本地启动

最小依赖启动方式（不是生产部署方案）：

```sh
docker compose up --build
```

租户／潜户端访问 `http://localhost:8080/tenant/`，员工端访问
`http://localhost:8080/staff/`；根路径重定向到租户端，网关存活检查为 `/gateway-health`。
Identity 已作为独立容器运行，外部接口统一使用 `/api/v1/auth/*`、`/api/v1/me*` 和
`/api/v1/iam/*`；`/internal/v1/*` 不通过公网 Gateway。Compose 自动执行 Alembic 并初始化
数据库，不搬迁或删除旧 MySQL 数据。MinIO 控制台 `http://localhost:9001` 与 S3
`localhost:9000` 同样由 Nginx 代理，三个端口仅绑定宿主机 127.0.0.1。

PostgreSQL 17 使用独立 `postgres17_p0_data` 卷，Redis 使用 `redis_p0_data`；二者只在 Compose
内网开放。旧数据库卷不会挂载或迁移，不要跨大版本复用物理数据目录。需要 DataGrip 时使用
显式的本地调试 override 临时绑定回环端口，不把数据库端口加入默认 Compose。

## 语言与地区设置

平台默认使用简体中文和中国大陆地区体验：

- `DEFAULT_LOCALE=zh-CN` 控制默认地区；`LLM_OUTPUT_LANGUAGE=Simplified Chinese` 控制模型面向用户的输出语言。
- `APP_TIMEZONE=Asia/Shanghai` 控制应用时间；`POSTGRES_TIMEZONE=Asia/Shanghai` 同时控制 PostgreSQL 会话时间、数据库日志和容器日志时区。
- 前端文案集中在 `frontend/src/i18n/index.js`。英文原文作为稳定资源键，当前提供 `zh-CN` 资源并预留 `en-US`；新增语言时添加资源表并加入 `supportedLocales`，无需修改业务数据字段。
- 后端模型语言策略集中在 `backend/app/localization.py`。JSON 键名和协议枚举保持稳定，模型生成的标题、解释、报告文本和问答内容按配置语言输出。

可复用切换组件位于 `frontend/src/components/LanguageSwitcher.jsx`。界面默认使用简体中文，并在登录、注册、个人资料和主界面显示一键中英文切换入口；如特定部署不需要切换功能，可设置 `VITE_ENABLE_LANGUAGE_SWITCH=false` 后重新构建前端将其隐藏。

测试拓扑仍从 Nginx 进入，并与默认单入口保持一致：

```sh
docker compose -f docker-compose.yml -f docker-compose.test.yml up --build
```

地址仍为 `/staff/` 和 `/tenant/`；微服务、PostgreSQL、Redis 均不发布宿主端口。日常浏览器
调试不要绕过 Gateway 直连 BFF 或领域服务。

宿主机仅运行离线检查时使用 Python 3.11+（本轮测试 3.13）、Node.js 22.12+；安装 `backend/requirements-dev.txt` 和前端 `npm ci`。需要宿主机后端调试时，在唯一根 env 设置 Nginx 上游为 `host.docker.internal:<端口>`、MinIO 客户端为 `localhost:<GATEWAY_S3_PORT>`；数据库仍须显式配置隔离连接，不通过 CORS 解决。

## 验证

```sh
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
cd frontend
npm run lint
npm run build
```

集成测试需通过进程变量 `TEST_DATABASE_URL` 指向已执行 Alembic 的隔离 PostgreSQL 库，并通过 `MINIO_*` 指向隔离 MinIO。未提供测试库时，集成测试明确跳过，不能视为完整验收；测试会新增测试用户/对象，请勿使用日常数据服务。

## 边界

- 上传原始 body：视频用 `video/*` 返回 `video_asset_id`，PDF 用 `application/pdf`。不是 multipart。
- 报告分析提交资源 ID，不接受本地路径。资源读取需 bearer token；前端图片使用受控 Blob URL，不公开 MinIO buckets。
- 默认支持最长 100 分钟、最大 8 GiB、最高 4K 的视频。源文件经磁盘临时文件流式传输，最多自适应抽取 1200 帧；上传与分析并发默认均为 1。相关阈值统一由根 `.env` 的 `MAX_UPLOAD_BYTES`、`MAX_VIDEO_SECONDS`、`MAX_VIDEO_PIXELS`、`MAX_EXTRACTED_FRAMES`、`VIDEO_*` 配置。
- 源码、模型权重、依赖及静态资源是程序资源，仍在项目/镜像；MinIO 自己的数据卷也是本地私有存储。
- 保留原提示词、模型分层、评分及三轮修复语义。原“最后一次修复后不再校验”仍存在，不能把完成事件当作报告校验合格。
- 未完成任务不保证进程重启后恢复；不引入生产队列、灰度方案或历史数据迁移。
