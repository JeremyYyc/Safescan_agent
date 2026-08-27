# Safe Scan Agent

面向家庭安全视频分析的前后端项目。后端负责视频处理、检测与报告生成，前端提供可视化交互界面。

## 技术栈
- 前端：React 19 + Vite + React Router + ESLint
- 后端：FastAPI + Uvicorn + Pydantic + PyMySQL
- AI/视觉：DashScope(Qwen) + Ultralytics YOLOv8 + OpenCV + PyTorch
- 数据库：MySQL

## 运行前准备
- Node.js 18+（或更高）
- Python 3.10+（或更高）
- MySQL 8.x（或兼容版本）

## 环境变量配置
Docker 部署统一使用仓库根目录的环境文件。变量清单、开发/测试/生产文件约定、Compose 注入方式和密钥规则见[Docker 统一环境配置技术文档](./docs/technical/15-environment-configuration.md)。

本地 Docker 启动前请基于 `.env.example` 创建根目录 `.env`；生产使用由部署系统注入的 `.env.production`。不要在 `backend` 或 `frontend` 目录单独维护部署环境文件。

裸机启动仅作为兼容路径；其环境加载逻辑仍可读取 backend 目录下的 env，但 Docker 部署和生产运维以根目录 env 文件为唯一配置来源。

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
项目已支持 `db + backend + frontend + gateway` 微服务编排，并区分测试/生产环境。

### 测试环境
```powershell
docker compose -f docker-compose.yml -f docker-compose.test.yml up --build
```

访问地址：
- 前端：`http://localhost:5173`
- 后端：`http://localhost:8000`
- MySQL：`localhost:3306`

### 生产环境
```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

访问地址：
- 网关（统一入口）：`http://localhost:8080`
- 健康检查：`http://localhost:8080/health`

## 数据库初始化（MySQL）
示例（可按需调整用户名/密码/库名）：
```sql
CREATE DATABASE IF NOT EXISTS safescan_agent DEFAULT CHARACTER SET utf8mb4;
-- CREATE USER 'safe_scan'@'localhost' IDENTIFIED BY 'your_password';
-- GRANT ALL PRIVILEGES ON safescan_agent.* TO 'safe_scan'@'localhost';
```

### 数据库升级注意事项
- 本仓库有两次不同的数据库升级，请按顺序执行，避免混用脚本。
- 升级 1（历史分支：UUID 文件隔离）：
  - Git 分支：`refactor/upload-dir`
  - 参考提交（short SHA）：`30e9f5b`
  - 后续相关分支：`refactor/uuid-set-encry`（`3723fd5`）
  - 目标：为用户补齐 `storage_uuid`，并将上传目录按用户 UUID 隔离。
  - 脚本：`backend/scripts/migrate_uploads_to_user_storage.py`
  - 预演：`python backend/scripts/migrate_uploads_to_user_storage.py`
  - 应用：`python backend/scripts/migrate_uploads_to_user_storage.py --apply`
- 升级 2（本次分支：`reports` 工程化拆分）：
  - Git 分支：`fix/refactor/report`
  - 参考提交（short SHA）：`9bc98b6`
  - 目标：将 `reports` 旧混合字段迁移到结构化模型（`report_analysis` / `report_pdf` / `report_assets` 等）。
  - 执行清单：`backend/docs/report_storage_refactor_rollout.md`
  - 迁移脚本：`backend/scripts/migrate_reports_storage_v2.py`
  - 预演：`python backend/scripts/migrate_reports_storage_v2.py`
  - 应用：`python backend/scripts/migrate_reports_storage_v2.py --apply`
  - 旧列清理（稳定后）：`backend/scripts/drop_legacy_report_columns.py`
  - 清理预演：`python backend/scripts/drop_legacy_report_columns.py`
  - 清理应用：`python backend/scripts/drop_legacy_report_columns.py --apply`
- 旧库升级推荐顺序：
  - 1) 先备份数据库（强烈建议）。
  - 2) 先执行升级 1（UUID 路径迁移）。
  - 3) 再执行升级 2（报告结构迁移）。
  - 4) 重启后端并回归：聊天列表、报告加载、PDF 上传/导出/下载。
  - 5) 观察稳定后，再执行 `drop_legacy_report_columns.py` 删除旧列。
  - 6) Windows + venv 建议用 `.\.venv\Scripts\python.exe` 运行脚本，避免系统 Python 缺依赖。


## 其他说明
- 上传与处理中间文件会保存到 `backend/uploads/`（运行时自动创建）。
- 上传目录按用户隔离：`backend/uploads/{storage_uuid}/Videos` 与 `backend/uploads/{storage_uuid}/PDF/uploaded`（导出 PDF 位于 `backend/uploads/{storage_uuid}/PDF/generated`）。
- 用户表新增 `storage_uuid`（UUIDv7）用于文件隔离，旧用户会在服务启动后自动补齐。
- `UUIDv7` 默认通过 `uuid6` 包生成；若不可用会回退到本地 UUIDv7 兼容实现。
- 删除聊天或删除上传 PDF 源时，后端会在删库后尝试回收 `uploads` 目录下相关文件。
- 视觉模型权重位于 `backend/app/yolov8m.pt`，首次运行可能较慢；GPU 可显著提升速度。
- 若前端端口不是 5173，需在 `backend/main.py` 中更新 CORS 白名单。
