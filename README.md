# Safe Scan Agent

家庭安全视频分析 Demo：上传视频 → 内存抽帧/筛选/视觉理解 → 多角色分析 → 完整报告，支持报告问答与按需 PDF。

## 当前技术栈

- 前端：React 19、Vite 7、React Router、DOMPurify。
- 编排：LangGraph 1.2.11；报告、上传、聊天、PDF 及模型工具循环均使用图。
- 后端：FastAPI、Pydantic、OpenAI-compatible Qwen 客户端。
- 数据：PostgreSQL 17、SQLAlchemy 2、psycopg 3、Alembic。
- 文件：私有 MinIO；视频/图片/PDF 使用内存流，无应用侧业务文件落盘。
- 视觉与 PDF：原 YOLOv8m、OpenCV、PyTorch、PyAV、ReportLab。

架构、节点、数据库和路径说明见 [当前技术与路径索引](docs/ARCHITECTURE.zh-CN.md)；阶段验收见 [执行记录](docs/REFACTOR_EXECUTION.zh-CN.md)。

## 唯一配置

复制根目录 `.env.example` 为根 `.env`，填写 PostgreSQL、MinIO、Qwen 与鉴权密钥。真实 `.env` 已被 Git 和镜像构建排除；不要创建 backend/frontend 或 test/production 环境副本。

- `Settings` 统一读取，优先级：显式覆盖 → 进程环境 → 根 `.env` → 默认值。
- 容器使用 `db:5432`、`minio:9000`；宿主机开发需将根配置主机改为 `localhost` 和映射端口。数据库 URL 中密码需要 URL 编码。
- `AUTH_SECRET`、`PUBLIC_ID_SECRET` 使用随机长密钥，不能留空；改变它们会使旧 token/公开 ID 失效。
- `VITE_API_BASE` 是唯一前端公开配置，默认空值走同源；更改后重新构建前端。
- 未启用的历史本地配置仅作为注释留存，不参与运行。

## 本地启动

最小依赖启动方式（不是生产部署方案）：

```sh
docker compose up --build
```

访问 `http://localhost:8080`，存活检查 `/health`。Compose 自动执行 Alembic 并初始化私有 buckets，不搬迁或删除旧 MySQL 数据。

宿主机开发使用 Python 3.11+（本轮测试 3.13）、Node.js 22.12+：

```sh
# 仅启动本地数据服务；注意把根 .env 的主机设置为宿主机地址
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d db minio
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt
PYTHONPATH=backend backend/.venv/bin/python -m alembic -c backend/alembic.ini upgrade head
PYTHONPATH=backend backend/.venv/bin/python -m uvicorn main:app --app-dir backend --reload --port 8000
```

另一个终端：

```sh
cd frontend
npm ci
npm run dev
```

前端开发地址 `http://localhost:5173`，Vite 将 `/api` 代理到后端 8000。数据库映射 5433，MinIO 映射 9000/9001。历史 test/prod override 仅保留本地端口/重启差异，仍共享根配置。

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
