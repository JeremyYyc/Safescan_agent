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
### 后端 `backend/.env`
后端会加载 `backend/.env`（或 `backend/app/.env`）：

```env
# 必填：DashScope API Key（阿里云通义）
DASHSCOPE_API_KEY=your_dashscope_api_key

# 选填：模型选择（默认 qwen-plus）
ALIBABA_TEXT_MODEL=qwen-plus
ALIBABA_MODEL=qwen-plus
ALIBABA_VISION_MODEL=qwen-vl-plus

# 必填：数据库连接
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/safe_scan?charset=utf8mb4

# 选填：鉴权签名密钥（强烈建议设置）
AUTH_SECRET=change-me-to-a-random-string
```

说明：
- `DATABASE_URL` 使用 MySQL 连接串，代码会在首次访问时自动建表，但数据库本身需提前创建。
- 模型相关变量未设置时会使用默认值。

### 前端 `frontend/.env`
```env
VITE_API_BASE=http://localhost:8000
```

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

## 数据库初始化（MySQL）
示例（可按需调整用户名/密码/库名）：
```sql
CREATE DATABASE IF NOT EXISTS safe_scan DEFAULT CHARACTER SET utf8mb4;
-- CREATE USER 'safe_scan'@'localhost' IDENTIFIED BY 'your_password';
-- GRANT ALL PRIVILEGES ON safe_scan.* TO 'safe_scan'@'localhost';
```

## 其他说明
- 上传与处理中间文件会保存到 `backend/uploads/`（运行时自动创建）。
- 视觉模型权重位于 `backend/app/yolov8m.pt`，首次运行可能较慢；GPU 可显著提升速度。
- 若前端端口不是 5173，需在 `backend/main.py` 中更新 CORS 白名单。
