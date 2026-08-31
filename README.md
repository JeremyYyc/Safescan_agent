# Safe Scan Agent

面向家庭安全视频分析的前后端项目。后端负责视频处理、检测与报告生成，前端提供可视化交互界面。

## 技术栈
- 前端：React 19 + Vite + React Router + ESLint
- 后端：FastAPI + Uvicorn + Pydantic + SQLAlchemy 2 + psycopg 3 + Alembic
- AI/视觉：DashScope(Qwen) + Ultralytics YOLOv8 + OpenCV + PyTorch
- 数据库：PostgreSQL

## 运行前准备
- Node.js 18+（或更高）
- Python 3.10+（或更高）
- PostgreSQL 17

## 环境变量配置

只维护根目录 `.env`，从 `.env.example` 复制并填写密钥。后端集中从 `app/settings.py` 读取；优先级：显式覆盖 → 进程环境 → 根 .env → 默认值。不要创建 backend/frontend 的 env 文件。

- `AUTH_SECRET`、`PUBLIC_ID_SECRET` 使用随机长密钥；不要提交真实值。
- `DATABASE_URL` 使用 postgresql+psycopg；容器主机名为 db，宿主机开发使用 localhost 和映射端口。
- `VITE_API_BASE` 留空走同源；Vite 开发代理转发到 8000，容器通过 gateway 转发。
- 仅公开的 VITE_API_BASE 进入前端构建。修改根 env 后重启后端或重新构建前端。
- 测试通过 Settings 注入覆盖，不创建第二套配置。

## 安装与启动
### 1) 后端
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

启动服务：
```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2) 前端
```powershell
cd frontend
npm install
npm run dev
```

若有报错，尝试使用：
```powershell
npm.cmd install
npm.cmd run dev
```

前端默认地址：`http://localhost:5173`  
后端默认地址：`http://localhost:8000`

## Docker 微服务部署
本地 Demo 使用 `docker compose up --build`。历史 override 文件仅调整端口/启动方式，共用根 `.env`，不维护测试/生产配置副本。

### 测试环境
```powershell
docker compose -f docker-compose.yml -f docker-compose.test.yml up --build
```

访问地址：
- 前端：`http://localhost:5173`
- 后端：`http://localhost:8000`
- PostgreSQL：`localhost:5433`

### 网关运行方式
```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

访问地址：
- 网关（统一入口）：`http://localhost:8080`
- 健康检查：`http://localhost:8080/health`

## 数据库初始化与测试

```sh
# 在根目录执行；仅创建/升级新 Demo schema，无旧数据搬迁
PYTHONPATH=backend backend/.venv/bin/python -m alembic -c backend/alembic.ini upgrade head
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
# PostgreSQL 集成测试需要 TEST_DATABASE_URL 指向隔离测试库
```

Compose 后端启动时执行 Alembic；业务请求不执行 DDL。十张表定义见 backend/app/persistence/schema.py，数据库访问位于 persistence/repositories.py，db.py 保持应用入口稳定。旧 MySQL 升级脚本已退出源码，历史可从 Git 获取。

## 业务资源与文件

视频、抽帧和标注图片、上传/导出 PDF 全部位于私有 MinIO。应用只使用内存流；不挂载 uploads，不生成本地业务临时文件。模型权重、源码和前端静态资源属于程序资源。

上传视频接口接收原始视频 body，返回 video_asset_id；分析接口提交此 ID。PDF 上传使用 application/pdf 原始 body。图片使用 /api/assets/{id}，需携带登录 token；前端读取后显示 Blob URL。MinIO bucket 不公开。

单文件处理同时受 MAX_UPLOAD_BYTES 和 MAX_VIDEO_MEMORY_BYTES 限制，默认 256 MiB；视频时长默认 600 秒、分辨率最多 8294400 像素。VIDEO_WORKER_CONCURRENCY 控制并发，需按内存配置。Nginx 关闭业务请求/响应磁盘缓冲。

模型权重位于 backend/app/yolov8m.pt；没有修改模型及检测/过滤规则。全部迁移与验证进展见 docs/REFACTOR_EXECUTION.zh-CN.md。
