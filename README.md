# Safe Scan Agent

家庭安全视频分析 Demo：上传视频 → 内存抽帧/筛选/视觉理解 → 多角色分析 → 完整报告，支持报告问答与按需 PDF。

## 当前技术栈

- 前端：React 19、Vite 7、React Router、DOMPurify。
- 编排：LangGraph 1.2.11；报告、上传、聊天、PDF 及模型工具循环均使用图。
- 后端：FastAPI、Pydantic、OpenAI-compatible Qwen 客户端。
- 数据：PostgreSQL 17、SQLAlchemy 2、psycopg 3、Alembic。
- 文件：私有 MinIO；视频/图片/PDF 使用内存流，无应用侧业务文件落盘。
- 视觉与 PDF：原 YOLOv8m、OpenCV、PyTorch、PyAV、ReportLab。

架构、节点、数据库和路径说明见 [当前技术与路径索引](docs/ARCHITECTURE.zh-CN.md)；代理入口和扩展方式见 [Nginx 网关](docs/NGINX_GATEWAY.zh-CN.md)；阶段验收见 [执行记录](docs/REFACTOR_EXECUTION.zh-CN.md)。

## 唯一配置

复制根目录 `.env.example` 为根 `.env`，填写 PostgreSQL、MinIO、Qwen 与鉴权密钥。真实 `.env` 已被 Git 和镜像构建排除；不要创建 backend/frontend 或 test/production 环境副本。

- `Settings` 统一读取，优先级：显式覆盖 → 进程环境 → 根 `.env` → 默认值。
- 容器数据库使用 `db:5432`；后端 MinIO 客户端使用 `gateway:9000`，不能绕过网关连接存储网络。数据库 URL 中密码需要 URL 编码。
- `AUTH_SECRET`、`PUBLIC_ID_SECRET` 使用随机长密钥，不能留空；改变它们会使旧 token/公开 ID 失效。
- 前端固定同源 `/api`，没有 `VITE_API_BASE` 或 CORS 配置；根 env 不向浏览器公开。
- 未启用的历史本地配置仅作为注释留存，不参与运行。

## 本地启动

最小依赖启动方式（不是生产部署方案）：

```sh
docker compose up --build
```

访问 `http://localhost:8080`，后端存活检查 `/health`，网关存活检查 `/gateway-health`。Compose 自动执行 Alembic 并初始化私有 buckets，不搬迁或删除旧 MySQL 数据。MinIO 控制台 `http://localhost:9001` 与 S3 `localhost:9000` 同样由 Nginx 代理，三个端口仅绑定宿主机 127.0.0.1。

开发模式仍从 Nginx 进入（同一个根 env），前端源码挂载支持热更新：

```sh
docker compose -f docker-compose.yml -f docker-compose.test.yml up --build
```

地址仍为 `http://localhost:8080`；Vite 在容器内 80 端口运行，其 HTTP/WebSocket 都经 Nginx，不发布 5173 或后端 8000。数据库与 MinIO 不直接发布端口。日常浏览器调试不要直接打开 Vite 或后端端口。

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
- 默认单文件 256 MiB、视频 600 秒/8294400 像素；上传与分析并发分别默认 2。限额按进程计算，按内存配置。
- 源码、模型权重、依赖及静态资源是程序资源，仍在项目/镜像；MinIO 自己的数据卷也是本地私有存储。
- 保留原提示词、模型分层、评分及三轮修复语义。原“最后一次修复后不再校验”仍存在，不能把完成事件当作报告校验合格。
- 未完成任务不保证进程重启后恢复；不引入生产队列、灰度方案或历史数据迁移。
