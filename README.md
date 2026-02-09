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

用户需要自己创建一个.env文件，在backend目录下，内容如下：
```env
# 必填：DashScope API Key（阿里云通义）
DASHSCOPE_API_KEY=your_dashscope_api_key  # 用户需自己到阿里云通义模型平台申请，替换为自己的 API Key

# 选填：OpenAI Key（如不使用 OpenAI 可留空，代码里暂无使用到OpenAI Key的场景）
OPENAI_API_KEY=your_openai_api_key_here

# 模型选择（DashScope），这些模型都可以切换任意千问旗下的相关模型（语义模型使用文本处理，图像识别使用视觉模型）进行使用，这里只是做推荐
ALIBABA_MODEL_L1=qwen-turbo-latest
ALIBABA_MODEL_L2=qwen-plus-latest
ALIBABA_MODEL_L3=qwen-max-latest
ALIBABA_MODEL_VL=qwen3-vl-plus

# 代理并发（控制每次任务内部 LLM 并发）
AGENT_MAX_CONCURRENCY=5

# 存储目录（这里是相对 backend 目录的 uploads 目录，如果要修改为其他的绝对路径，需要在 backend/main.py 中同步修改）
OUTPUT_DIR=uploads

# 数据库连接
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/safescan_agent?charset=utf8mb4

# 鉴权签名密钥（强烈建议设置为随机字符串或者随机生成的 UUID，自定义的字符串也可以，但不要外传或泄露）
AUTH_SECRET=change-me-to-a-random-string

# 鉴权有效期（小时）
AUTH_EXPIRE_HOURS=8
```

说明：
- `DATABASE_URL` 使用 MySQL 连接串，代码会在首次访问时自动建表，但数据库schema本身需提前创建。
- `OUTPUT_DIR` 需要可写目录（相对 backend 根目录）。
- `AGENT_MAX_CONCURRENCY` 过大可能触发模型接口限流或显存不足，建议从 2–5 试起。
- **不要把真实密钥提交到仓库**，部署时请替换为你自己的值。

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
CREATE DATABASE IF NOT EXISTS safescan_agent DEFAULT CHARACTER SET utf8mb4;
-- CREATE USER 'safe_scan'@'localhost' IDENTIFIED BY 'your_password';
-- GRANT ALL PRIVILEGES ON safescan_agent.* TO 'safe_scan'@'localhost';
```

## 其他说明
- 上传与处理中间文件会保存到 `backend/uploads/`（运行时自动创建）。
- 上传目录按用户隔离：`backend/uploads/{storage_uuid}/Videos` 与 `backend/uploads/{storage_uuid}/PDF`。
- 用户表新增 `storage_uuid`（UUIDv7）用于文件隔离，旧用户会在服务启动后自动补齐。
- `UUIDv7` 默认通过 `uuid6` 包生成；若不可用会回退到本地 UUIDv7 兼容实现。
- 历史文件迁移脚本：`backend/scripts/migrate_uploads_to_user_storage.py`
  - 预演（不改文件/数据库）：`python backend/scripts/migrate_uploads_to_user_storage.py`
  - 正式迁移：`python backend/scripts/migrate_uploads_to_user_storage.py --apply`
- 删除聊天或删除上传 PDF 源时，后端会在删库后尝试回收 `uploads` 目录下相关文件。
- 视觉模型权重位于 `backend/app/yolov8m.pt`，首次运行可能较慢；GPU 可显著提升速度。
- 若前端端口不是 5173，需在 `backend/main.py` 中更新 CORS 白名单。
