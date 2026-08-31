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

## 其他说明
- 上传与处理中间文件会保存到 `backend/uploads/`（运行时自动创建）。
- 上传目录按用户隔离：`backend/uploads/{storage_uuid}/Videos` 与 `backend/uploads/{storage_uuid}/PDF/uploaded`（导出 PDF 位于 `backend/uploads/{storage_uuid}/PDF/generated`）。
- 用户和资源使用 UUIDv7；新库不包含旧用户迁移逻辑。
- `UUIDv7` 默认通过 `uuid6` 包生成；若不可用会回退到本地 UUIDv7 兼容实现。
- 删除聊天或删除上传 PDF 源时，后端会在删库后尝试回收 `uploads` 目录下相关文件。
- 视觉模型权重位于 `backend/app/yolov8m.pt`，首次运行可能较慢；GPU 可显著提升速度。
- 若前端端口不是 5173，在根 `.env` 中更新 CORS_ORIGINS。
