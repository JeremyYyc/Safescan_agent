# Safe Scan Agent：全项目技术分析

分析日期：2026-08-31。基线：`main`，提交 `79bf95f`。

> 历史基线文件。重构后的技术栈、已修复项目及剩余限制请阅读 [当前架构与路径索引](ARCHITECTURE.zh-CN.md) 和 [执行记录](REFACTOR_EXECUTION.zh-CN.md)。

本报告以当前仓库源码、依赖声明、前端 lockfile 和本地离线检查为依据，不把 README、环境变量或历史缓存中的描述直接视为已实现能力。未连接业务数据库、调用云模型、启动服务、执行迁移或修改业务代码。

配套文档：[代码与路径索引](/Users/jeremyyang/Project/Safescan_agent/docs/PATH_INDEX.zh-CN.md)。

## 1. 项目定位与总体判断

项目面向家庭安全视频分析，主要提供：

1. 用户注册、登录与个人资料修改。
2. 上传家庭环境视频，结合特定人群属性生成安全分析报告。
3. 保存报告、代表图片、会话和历史消息。
4. 对单份报告问答，以及在普通聊天中引用多份报告进行比较。
5. PDF 上传、导出、预览和下载。
6. 基于本地产品指南的检索式问答。

当前架构应准确描述为：**React SPA + FastAPI 模块化单体 + MySQL + 本地文件存储 + 云端千问模型 + 本地 YOLO 推理**。

Docker 将数据库、后端、前端静态站点、网关拆成四个容器，但业务后端仍然是一个 FastAPI 应用，并非多个独立业务微服务。视频任务在后端进程内的线程中运行，不是独立 Worker 服务。

整体已经具备较完整的产品功能组织和报告数据模型；但目前仍存在安全、配置、依赖可复现性、任务可靠性及接口契约问题。不能仅凭前端可构建或 `/health` 返回成功判断系统已具备生产可用性。

## 2. 分析范围与规模

基线下 Git 跟踪 89 个文件，其中：

| 类别 | 数量或规模 | 说明 |
| --- | --- | --- |
| Python 源文件 | 41 | 后端、工具、工作流和迁移脚本 |
| JSX 文件 | 11 | App、布局和页面 |
| CSS 文件 | 5 | 原生 CSS，不是 Tailwind |
| Compose 文件 | 3 | 基础、测试、生产 |
| 应用 API | 21 条 | 不含健康检查、静态资源与框架文档路由 |
| 数据表 | 10 张 | 依据当前建表代码，而非实时数据库 |
| 已跟踪测试源码 | 0 | 本地测试目录只有缓存，不能替代测试源码 |

主要复杂度集中在：

| 文件 | 行数 | 集中承担的职责 |
| --- | ---: | --- |
| [db.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py) | 2,089 | 连接、DDL、兼容迁移、用户、会话、报告、文件 CRUD |
| [App.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx) | 1,918 | 路由、鉴权、API 请求、状态、上传、流解析、报告操作 |
| [home.css](/Users/jeremyyang/Project/Safescan_agent/frontend/src/styles/home.css) | 1,630 | 主界面布局与样式 |
| [ChatLayout.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/layouts/ChatLayout.jsx) | 1,013 | 侧栏、会话操作、报告选择、搜索、弹层、Outlet 上下文 |
| [history.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/history.py) | 593 | 会话、消息、报告引用、PDF 上传和文件回收 |
| [ThreadContent.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/pages/ThreadContent.jsx) | 584 | 报告和聊天正文、图片、Markdown 渲染 |

这些规模是可维护性信号，不意味着“大文件本身就是功能错误”。主要问题是变化原因过多、测试边界不清晰。

## 3. 技术栈清单

### 3.1 前端

版本分别区分“声明范围”和“lockfile 解析版本”，不代表上游最新版本。

| 技术 | 声明范围 | lockfile 版本 | 实际职责 |
| --- | --- | --- | --- |
| React / React DOM | `^19.2.0` | `19.2.3` | 组件渲染、Hooks 状态管理 |
| React Router DOM | `^6.30.0` | `6.30.3` | BrowserRouter、嵌套路由、Outlet context |
| Vite | `^7.2.4` | `7.3.1` | 开发服务和生产构建 |
| Vite React 插件 | `^5.1.1` | `5.1.2` | JSX/React 构建支持 |
| ESLint | `^9.39.1` | `9.39.2` | JS、React Hooks 与 Refresh 检查 |
| marked | `^12.0.2` | `12.0.2` | 模型输出 Markdown 转 HTML |
| DOMPurify | `^3.0.11` | `3.3.1` | 清洗 Markdown 生成的 HTML |
| 原生 Fetch / ReadableStream | 浏览器 API | — | HTTP 请求和 NDJSON 流读取 |
| 原生 CSS | — | — | 页面、响应式布局与组件外观 |

源码使用 JavaScript/JSX，不是 TypeScript。存在 `@types/react` 不等于项目已接入 TypeScript。未发现 Redux、Zustand、React Query、Axios、Next.js 或组件 UI 框架的实际使用。

依据：[package.json](/Users/jeremyyang/Project/Safescan_agent/frontend/package.json)、[package-lock.json](/Users/jeremyyang/Project/Safescan_agent/frontend/package-lock.json)、[main.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/main.jsx)。

### 3.2 后端、AI 和文件生成

| 技术 | requirements 声明 | 实际职责 |
| --- | --- | --- |
| Python | Docker 使用 `3.11-slim` | 后端运行时；README 写的是 3.10+ |
| FastAPI | `>=0.110.0` | API、依赖注入、静态文件、流响应 |
| Uvicorn | `>=0.27.0` | ASGI 服务 |
| Pydantic | `>=2.10.0,<3` | 部分请求 DTO；报告仍主要为字典 |
| python-multipart | `>=0.0.9` | 视频/PDF 表单上传 |
| PyMySQL | `>=1.1.0` | 同步连接 MySQL、手写 SQL |
| python-dotenv | `1.0.0` | 加载后端环境文件 |
| pyautogen | `>=0.7.0` | AutoGen 依赖入口；代码直接使用 agentchat/core |
| OpenAI Python SDK | `1.3.7` | 调用 DashScope 的 OpenAI 兼容端点 |
| DashScope SDK | `1.19.1` | 聊天意图识别与回答生成 |
| httpx | `0.25.0` | HTTP 客户端依赖 |
| Ultralytics | `>=8.1.0` | YOLO 模型加载和目标检测 |
| PyTorch | `>=2.2.0` | YOLO 的推理运行依赖 |
| OpenCV | `>=4.9.0.80` | 解码、抽帧、画框、清晰度/亮度/人脸筛选 |
| Pillow / NumPy | `>=10.1.0` / `>=1.26.4` | 图像读写和数值处理 |
| ImageHash | `4.3.1` | 感知哈希去重 |
| ReportLab | `>=4.1.0` | 从结构化报告生成 PDF |
| uuid6 | `>=2024.7.10` | UUIDv7；另有本地兼容实现 |
| cryptography | `>=41.0.3` | 声明的依赖；应用鉴权本身使用标准库 HMAC |

注意：使用 OpenAI SDK 不代表使用 OpenAI 模型。本项目相关代码连接的是 `https://dashscope.aliyuncs.com/compatible-mode/v1`，读取 `DASHSCOPE_API_KEY`。未发现业务代码读取 `OPENAI_API_KEY`。

### 3.3 存储和基础设施

| 技术 | 当前状态 |
| --- | --- |
| MySQL | Compose 使用 `mysql:8.0`，InnoDB、utf8mb4、JSON 列 |
| 文件存储 | 后端本地文件系统；Docker 使用命名卷持久化 |
| Nginx | 前端静态服务一层、统一入口网关一层，镜像 `1.27-alpine` |
| Docker Compose | 四容器编排；test/prod 覆盖文件 |
| Node.js | 前端 Docker 构建使用 `node:20-alpine` |
| PostgreSQL / Redis / Celery / MinIO | 仅在根目录本地 `.env` 发现配置，不属于当前已接入技术栈 |
| 向量库 / Embedding / Reranker | 未发现实际接入 |
| CI/CD、集中日志、指标平台 | 未发现仓库内配置或接入实现 |

## 4. 系统架构与边界

当前生产编排的设计关系：

```text
浏览器
  → 网关 Nginx（宿主机 8080 → 容器 80）
      ├─ /              → frontend:80 → React 静态资源 / SPA 回退
      ├─ /api/*         → backend:8000 → FastAPI
      ├─ /uploads/*     → backend:8000 → StaticFiles
      └─ /health*       → backend:8000

FastAPI
  ├─ PyMySQL → db:3306 → mysql_data 卷
  ├─ 本地文件读写 → /app/uploads → backend_uploads 卷
  ├─ 本地视频处理 → OpenCV + YOLO + PyTorch
  └─ 外部模型调用 → DashScope / 千问
```

此图描述配置意图，不等于当前前端 API 地址一定正确；空 `VITE_API_BASE` 的回退逻辑与同源网关方案有冲突，详见第 12 节。

关键边界：

- 鉴权与业务操作：通过 Bearer token 和数据库用户/资源归属检查。
- 文件处理：视频路径会校验是否位于当前用户的 `Videos` 目录。
- 文件访问：整个 `/uploads` 目录被静态挂载，没有对应鉴权依赖。
- 云端数据：代表图片通过模型客户端转换为图像消息发送至 DashScope；并非全流程本地分析。
- 多任务并发：进程内线程和集合锁，无跨进程协调。

## 5. 前端技术分析

### 5.1 路由设计

| 浏览器路径 | 页面 | 行为 |
| --- | --- | --- |
| `/` | App 重定向 | 根据 token 转到聊天或登录 |
| `/login` | Login | 登录 |
| `/register` | Register | 注册 |
| `/chat` | ChatLayout + ChatIndexPage | 普通聊天入口 |
| `/chat/:threadId` | ChatThreadPage + ThreadContent | 普通聊天、报告引用和比较 |
| `/report/new` | ReportNewPage + ThreadContent | 新建视频报告草稿 |
| `/report/:threadId` | ReportThreadPage + ThreadContent | 报告详情、问答、PDF 操作 |
| `/profile` | Profile | 修改用户名 |
| 未匹配路径 | App 重定向 | 转聊天或登录 |

入口链：[index.html](/Users/jeremyyang/Project/Safescan_agent/frontend/index.html) → [main.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/main.jsx) → [App.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx)。

### 5.2 状态与组件关系

App 管理鉴权、会话列表、当前报告、视频、用户属性、流式进度、聊天消息、PDF 状态等。大量属性传给 ChatLayout，再通过 `Outlet context` 传给页面。页面组件大多负责路由初始化，正文集中在 ThreadContent。

优点：控制链明确，不依赖额外状态管理框架。代价：App 变成“状态 + 请求 + 业务 + 路由”的综合控制器，聊天和报告两处布局配置有大量重复，单元测试与局部迭代成本较高。

适合逐步拆成 `api/`、`hooks/` 和 `features/auth|chat|report/`，而不是先引入复杂状态框架再继续堆叠逻辑。

### 5.3 网络与渲染行为

- `apiFetch()` 添加 Authorization，处理 401 并清理登录态。
- `safeScanAuthToken`、`safeScanAuthUser` 保存于 localStorage。
- 视频分析使用 POST + `ReadableStream` 按行解析 NDJSON；不是 SSE，也不是 WebSocket。
- 普通聊天等待完整 JSON 后，以定时器每次追加字符形成打字效果；不是模型 token 实时流式输出。
- 模型回答经过 `marked.parse()` 和 `DOMPurify.sanitize()` 后渲染。这是已有的有效 HTML 清洗措施。
- 图片地址由 `toUploadUrl()` 从磁盘路径中截取 `/uploads/` 拼接，前端与后端物理目录名字存在耦合。
- 未发现统一请求取消机制，长任务断开与页面切换的资源生命周期需要继续完善。

依据：[App.jsx 网络封装](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:377)、[视频分析](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:1465)、[聊天](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:1582)、[Markdown 清洗](/Users/jeremyyang/Project/Safescan_agent/frontend/src/pages/ThreadContent.jsx:87)。

## 6. 后端分层分析

### 6.1 入口与模块

`main.py` 创建 FastAPI 应用，注册 report、chat、history、auth、guide 五组路由，统一增加 `/api` 前缀，并挂载文件目录。

| 层次 | 位置 | 职责 |
| --- | --- | --- |
| 应用组装 | `main.py` | 路由、CORS、静态资源、健康检查 |
| HTTP 接口 | `app/api/` | 参数、认证、业务控制、响应 |
| 工作流 | `app/workflow/` | 视频步骤、多角色编排、状态和修复循环 |
| 模型角色与适配 | `app/agents/` | 文本/视觉角色和模型协议转换 |
| Prompt | `app/prompts/` | 输出约束、角色任务和问答策略 |
| 工具 | `app/tools/` | 视觉算法、报告结构校验 |
| 知识库 | `app/knowledge/` | 产品指南和词项检索 |
| PDF | `app/pdf/` | ReportLab 排版 |
| 数据访问 | `app/db.py` | 全部数据表的 SQL 与兼容逻辑 |
| 公共基础 | `app/auth.py`、`env.py`、`utils/` | token、环境、公开 ID、UUID |

已经做了文件级拆分，但还不是完整的 Controller → Service → Repository 分层：例如 report API 同时负责线程、文件、模型流程、标题生成、存库和 PDF 导出，history API 同时负责关系操作与物理文件回收。

### 6.2 同步/异步模型

- 视频处理通过 `threading.Thread(..., daemon=True)` 离开 HTTP 事件循环。
- 后台线程向 `queue.Queue` 写事件，响应协程通过 `run_in_executor` 读取并返回。
- specialist 阶段使用 `asyncio.gather` 并发，OpenAI 同步 SDK 调用通过 `asyncio.to_thread` 包装。
- 普通聊天接口虽然是 `async def`，内部仍直接执行同步数据库访问、DashScope 请求和 `time.sleep` 重试。
- PDF 导出也是异步接口，但直接调用同步 Agent 和 ReportLab 排版。

因此，“FastAPI + async def”不等于所有 I/O 都已非阻塞。当前长耗时任务隔离只覆盖部分链路。

## 7. 视频分析与多角色 AI 工作流

### 7.1 完整调用链

```text
App.handleRunAnalysis
  → POST /api/uploadVideo
  → POST /api/processVideoStream
      → 检查会话归属 / 是否已有报告 / 进程内任务占用
      → 创建 Videos/run_<uuid4>
      → 后台线程
          → WorkflowOrchestrator.execute_workflow
              → 抽帧 → 过滤 → 代表图选择 → YOLO 画框
              → SceneUnderstandingAgent（VL）
              → RouterAgent（L1）与角色计划兜底
              → Hazard + Comfort（L2，可并行）
              → Compliance + Scoring（L2，可并行）
              → Recommendation（L2）
              → ReportWriter（L3）
          → Validator + ReactRepairLoop（最多 3 轮）
          → 将区域与证据图片关联
          → TitleAgent（L2）
          → reports / report_analysis / files / report_assets / chat_details
          → complete / end 事件
```

Comfort、Compliance、Scoring、Recommendation 是否运行由计划决定；Hazard 和 ReportWriter 被强制保留。Recommendation 被选中时会补入 Scoring。

### 7.2 视频算法细节

| 步骤 | 当前实现 | 技术含义 |
| --- | --- | --- |
| 抽帧 | 目标 1 帧/秒，遍历视频解码 | 帧数与视频时长相关；不是实时视频流处理 |
| 相似过滤 | pHash 汉明距离阈值 25 | 删除近似帧，减少后续模型输入 |
| 模糊过滤 | Laplacian 方差阈值 50 | 过滤低清晰度帧 |
| 暗帧过滤 | HSV 亮度均值阈值 50 | 过滤过暗帧 |
| 敏感帧过滤 | Haar 人脸检测后删除整帧 | 不是人脸打码，也不是完整隐私保护方案 |
| 场景分段 | HSV 直方图相关性阈值 0.78 | 外观变化启发式分段，不是训练好的房间分割模型 |
| 候选采样 | 每段最多 3 张，短段 1 张 | 控制候选数量 |
| 候选打分 | 清晰度 .35 + 亮度 .25 + 物体丰富度 .25 + 边缘密度 .15 | 手工加权质量排序 |
| 代表图选择 | 配置总数上限 15、每房间目标上限 3 | 基于 YOLO 物体推断房间；不是精确空间重建 |
| 目标检测 | 置信度大于 .5，写回原图片 | 标注会覆盖代表帧；原始视频仍保留 |

每房间 3 张是初选逻辑的目标：超出总量时重组候选的分支未持续强制这一上限，不能将其视为所有路径下的硬约束。

YOLO 权重为仓库中的 [yolov8m.pt](/Users/jeremyyang/Project/Safescan_agent/backend/app/yolov8m.pt)。未发现项目内训练/微调流水线、标注集或模型效果评估集；不要把目标检测描述为专门训练的家庭危险识别模型。危险解释主要来自后续千问分析。

算法限制：1 秒采样可能遗漏短暂事件；去重/暗帧/人脸过滤会牺牲部分证据；`sink` 等物体同时出现在多种房间，基于规则的房间判断可能偏置；场景分组主要是“房间类型”，不保证区分两个不同卧室。

### 7.3 模型分层与真实 Agent 形式

| 等级 | 使用位置 | 目的 |
| --- | --- | --- |
| L1 | Router、聊天意图分类、PDF repair | 轻量决策/格式修复 |
| L2 | Hazard、Comfort、Compliance、Scoring、Recommendation、Title、聊天回答 | 领域分析与文本输出 |
| L3 | ReportWriter、报告重写 | 综合报告生成 |
| VL | SceneUnderstandingAgent | 单图视觉理解和房间证据提取 |

模型名来自 `ALIBABA_MODEL_L1/L2/L3/VL`，代码没有模型名缺失时的默认值。README 中具体 Qwen 名称只是配置示例。

系统不是“所有角色都由 AutoGen 群聊自动协商”：

- Scene、Router、Writer、Title、PDF repair 使用 AutoGen AssistantAgent 封装。
- Hazard、Comfort、Compliance、Scoring、Recommendation 是 `agent_team.py` 中的角色化 Prompt 调用，没有各自独立 Python Agent 类。
- 编排顺序由 Python 代码控制，Router 只从白名单选择角色。
- 模型适配器声明不支持 function calling，传入 tools 会报错。
- `create_stream()` 是等待完整结果后输出，不是底层 token streaming。
- `count_tokens()` 返回 0，`remaining_tokens()` 返回固定值；尚无真实 token 预算管理。

这是一套“受控多角色工作流”，不是具备任意工具执行与自主探索能力的通用智能体系统。

### 7.4 报告结构与校验

报告包含 `regions`、`meta`、`scores`、`top_risks`、`recommendations`、`comfort`、`compliance`、`action_plan`、`limitations` 等字段。

区域字段包括：`regionName`、`potentialHazards`、`colorAndLightingEvaluation`、`suggestions`、`scores`。区域分数要求 5 个 0–5 的数字。前端保留了 `final_socre` 的拼写，应在统一数据契约时一并处理。

Validator 当前检查结构、部分字段和数值范围，不验证安全判断的事实准确性、法规适用性或建议有效性。ComplianceAgent 也未连接权威标准检索源，其名称不能视为合规认证。

`ReactRepairLoop` 是项目对“校验 → 生成修复提示 → 重写”的命名，与前端 React 无关。最后一轮重写后没有额外校验，达到轮数上限会返回 `success=False`。目前上层仍可能保存该结果并发送 complete。

## 8. 聊天、知识库与 PDF

### 8.1 聊天路由

`processChat` 读取最近 20 条用户问题构造记忆，使用 L1 识别 SAFETY、REPORT_EXPLANATION、GUIDE、GREETING、SMALLTALK、OTHER；问候/闲聊许可按最近消息统计，目标限制为 3 轮，并非严格的终生配额。

随后：

- 产品问题 → 检索指南 → L2 根据命中内容回答。
- 报告会话问题 → 当前报告 JSON 或区域信息。
- 普通 bot 会话的报告问题 → 活跃报告引用 → 多报告 JSON 比较。
- 安全问题 → 通用家庭安全 Prompt。
- 无关问题 → 固定拒答。

当前历史记忆不是完整“用户 + 助手”对话拼接，也没有长期摘要、向量记忆或按 token 截断的上下文预算。多份报告直接整体塞入 Prompt，报告数量增加后可能遇到上下文、成本和延迟问题。

### 8.2 本地知识检索

数据源：[quick_guide.json](/Users/jeremyyang/Project/Safescan_agent/backend/app/knowledge/quick_guide.json)。

`guide.py` 使用英文词项和中文单字切分、停用词过滤、自定义 BM25 风格排序；IDF 使用比例值而不是带对数的公式。章节内容缓存在进程内。

这是轻量词项检索增强问答，不是向量 RAG，也没有 PDF 分块索引、Embedding、向量数据库或 Reranker。

### 8.3 PDF 的能力边界

生成：结构化报告 → 字段归一化 → 尝试 L1 修复 → ReportLab 排版 → 存 PDF 元数据和关联 → 返回预览/下载地址。

上传：扩展名和 MIME 初步校验 → 保存文件 → `store_pdf_report(..., extracted_text="")`。

**上传 PDF 当前没有正文解析或 OCR。** 加入聊天后的 PDF 数据主要是标题和空的 `content_preview`；不能因为界面允许“添加 PDF 报告”，就认为模型已经阅读并理解其正文。系统导出的 PDF 保存了有限 preview，也不等同于 PDF 全文解析。

PDF 使用 Letter 页面和 Helvetica 等默认字体，主要为英文报告设计；没有看到中文字体注册。当前渲染导入与主体没有代表图片嵌入链路，应描述为以文本、表格和评分为主的 PDF。

## 9. 数据库模型与存储设计

### 9.1 十张表

| 表 | 关键字段 | 职责 |
| --- | --- | --- |
| users | user_id、email、username、password、storage_uuid | 用户与磁盘隔离标识 |
| chats | id、chat_uuid、user_id、chat_type、pinned、status | report/bot 两种会话 |
| messages | id、role、content、meta | 消息正文与意图元数据 |
| chat_details | chat_id、message_id、report_id、role | 会话时间线，连接消息/报告 |
| reports | id、report_uuid、user_id、report_kind、origin_chat_id、title、status | 统一报告主记录 |
| report_analysis | report_id、video_file_id、region_info_json、report_json | 视频分析报告子表 |
| report_pdf | report_id、file_id、pdf_kind、derived_from_report_id、content_preview | 上传/导出 PDF 子表 |
| files | file_uuid、user_id、storage_path、storage_path_hash、mime_type、file_size、sha256 | 文件元数据 |
| report_assets | report_id、file_id、asset_kind、sort_order | 报告图片等资源 |
| chat_report_refs | chat_id、report_id、source_chat_id、status | 跨会话报告引用 |

逻辑关系：用户拥有会话和报告；会话通过 chat_details 组织消息与报告；报告通过类型子表区分分析/PDF，通过 report_assets 关联文件；bot 会话通过 chat_report_refs 引用多个报告。

这些关系主要由业务 SQL 维护；当前建表代码未声明 FOREIGN KEY。`users.user_id` 与部分引用列整数类型也不完全一致，未来添加外键前应先统一。

### 9.2 已有设计亮点

- reports 主表与类型子表分离，避免分析 JSON、PDF 路径混在一张大表。
- files 集中管理物理路径，report_assets 支持顺序与类型。
- PDF 支持 `derived_from_report_id`，可以表达导出来源。
- 报告引用与报告实体分离，便于比较及解除引用。
- 部分读取已批量加载文件、报告和源会话，避免简单逐项查询。
- UUID 唯一索引、报告类型/来源索引、会话明细索引等已存在。

### 9.3 主要数据层问题

1. 每次业务函数普遍新建 PyMySQL 连接，未见连接池。
2. `_ensure_core_tables()` / `_ensure_report_table()` 在多种读写请求中反复调用，包含 SHOW、扫描回填，甚至无条件 ALTER；不是只在首次启动执行。
3. `autocommit=True`，报告写入涉及多张表却没有显式事务，异常时可能部分成功。
4. 进程内迁移锁不覆盖多进程、多副本，无法替代正式迁移机制。
5. 用户 email 没有数据库唯一约束，仅靠先查再写无法覆盖并发注册。
6. `storage_path_hash` 是路径字符串的 SHA-256，不是文件内容摘要；写入 `files.sha256` 时当前是 NULL，不能当作内容去重已实现。
7. 文件删除与数据库删除跨资源、非原子，虽然有引用检查和路径约束，但缺少失败重试/对账任务。

依据：[数据库连接](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:85)、[建表入口](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:116)、[报告 DDL](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:1752)、[报告写入](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:2017)。

### 9.4 ID 分层

- 数据库主键：整数，用于内部关联。
- UUIDv7：用户存储目录和会话/报告 UUID。
- 公开 ID：用户 `k2_`、会话 `m8_`、报告 `q5_` 前缀，使用掩码、Base64 和截断 HMAC 校验。
- 上传文件与运行目录：通常使用 UUIDv4 随机名称。

公开 ID 是自定义编码，不是标准加密令牌，也不应承担授权职责。兼容解析允许原始 32 位 UUID，部分入口还兼容整数；最终安全边界仍是用户归属检查。更换 `PUBLIC_ID_SECRET` 会影响既有公开链接解析，需有轮换/兼容策略。

## 10. 磁盘路径与 URL 映射

默认文件根目录为：`/Users/jeremyyang/Project/Safescan_agent/backend/uploads`；容器内为 `/app/uploads`。

```text
uploads/
  <user_storage_uuid>/
    Videos/
      originals/<uuid4>.<suffix>       上传原视频
      run_<uuid4>/frame_<n>.jpg        筛选后帧/画框后的代表图片
    PDF/
      uploaded/<uuid4>.pdf            上传 PDF
      generated/report_<chat>_<uuid4>.pdf
```

`OUTPUT_DIR` 为相对路径时，相对于 backend 目录解析；也支持绝对路径。`main.py` 导入同一个 OUTPUT_DIR 做静态挂载，因此 README 所说“修改绝对路径需同步改 main.py”并不符合当前实现。

默认 URL 为 `/uploads/<用户目录>/...`。视频上传接口返回的是服务器磁盘路径，分析请求再把这个路径传回服务器；相比传 `file_id`，这种接口更依赖部署路径，并暴露内部目录结构。

将 OUTPUT_DIR 改成不包含 `uploads` 的自定义目录时，后端静态挂载仍然是 `/uploads`，但前端 `toUploadUrl()` 的字符串截取可能失效。应在服务端统一返回资源 URL 或 file_id，而不是让前端推断路径。

本地 `.venv/`、`backend/.venv/`、`node_modules/`、`dist/`、`__pycache__/` 都是环境或生成产物，不是架构源码；本地存在这些文件不能证明全新部署可重现。

## 11. 配置与部署分析

### 11.1 环境变量加载关系

| 配置位置 | 当前读取方 | 说明 |
| --- | --- | --- |
| 根目录 `.env` | Compose 插值 | 不会被 `app.env.load_env()` 自动加载 |
| backend/app/.env | python-dotenv | 若存在则先加载 |
| backend/.env | python-dotenv | 若存在则以 `override=True` 加载，覆盖前者及已有同名环境变量 |
| backend/.env.test | test Compose `env_file` | 由 Compose 注入后端容器 |
| backend/.env.production | prod Compose `env_file` | 由 Compose 注入后端容器 |
| frontend/.env.production | Vite production mode | 构建期配置，不是运行期配置 |
| frontend/.env.test | Vite test mode 才读取 | `npm run dev` 不会自动切到 test；test Docker 实际通过 build arg 配置地址 |

根 `.env` 当前具有 PostgreSQL、Redis、Celery、MinIO、QWEN_* 等另一套配置命名。其 DATABASE_URL scheme 是 `postgresql+psycopg`，而当前后端只解析 MySQL；直接把这套配置作为后端环境将不匹配。不能仅移动文件就完成技术栈切换。

Compose 根 `.env` 中的 `VITE_API_BASE` 可通过生产 build arg 影响打包；“根 .env 不被后端加载”不等于“它完全不会影响部署”。

### 11.2 当前代码真正使用的配置

| 配置项 | 用途或默认行为 |
| --- | --- |
| DASHSCOPE_API_KEY | 模型鉴权 |
| ALIBABA_MODEL_L1/L2/L3/VL | 分层模型名，缺失会报错 |
| AGENT_MAX_CONCURRENCY | 场景处理入口读取，但默认被 `min(...,1)` 限制为串行 |
| DATABASE_URL | 仅 MySQL / mysql+pymysql |
| OUTPUT_DIR | 默认 backend/uploads |
| AUTH_SECRET | 未设置则退回开发默认密钥 |
| AUTH_EXPIRE_HOURS | 默认 8 小时 |
| PUBLIC_ID_SECRET | 公开 ID；次级回退 SECRET_KEY / APP_SECRET，再回退内置常量 |
| UUID7_FORCE_FALLBACK | 强制本地 UUIDv7 实现 |
| CORS_ORIGINS / CORS_ORIGIN_REGEX | 来源白名单及正则；默认允许多类局域网地址 |
| VITE_API_BASE | 浏览器 API 地址，构建时注入 |
| MYSQL_ROOT_PASSWORD / MYSQL_DATABASE | Compose 数据库初始化相关 |

根环境文件中的 `MAX_UPLOAD_BYTES`、`WORKFLOW_*`、`VIDEO_WORKER_CONCURRENCY` 等未见当前对应消费代码，不可据此认为上传限额、任务超时或 Worker 并发已经生效。

### 11.3 三种运行方式

| 模式 | 前端 | 后端 | 数据库 | 网关 |
| --- | --- | --- | --- | --- |
| 本地源码开发 | Vite，通常 5173 | Uvicorn 8000 | 自行准备 MySQL | 不必启用 |
| test Compose | Nginx 静态站点，5173 | 暴露 8000 | **3307 → 3306** | 默认 disabled profile |
| prod Compose | 内网 frontend:80 | 内网 backend:8000 | 内网 db:3306 | **8080 → 80** |

README 的测试 MySQL 宿主端口写成 3306，实际覆盖配置为 3307。测试 Docker 的前端不是 Vite 热更新服务器，而是构建后的静态站点。

前端 lockfile 对 Vite 和插件的 Node 要求为 `^20.19.0 || >=22.12.0`，README 的“Node 18+”不准确。Docker 使用浮动 `node:20-alpine`，不是补丁版本固定的可复现镜像。

测试与生产在同一目录运行且不指定不同 Compose project name 时，逻辑卷名/项目身份可能复用；切换环境不意味着自动拥有独立数据库卷。部署应显式隔离项目名、卷及配置，并验证已有 MySQL 数据卷的初始化状态。

### 11.4 容器化边界

- 后端依赖数据库 healthcheck；前端/网关 depends_on 没有等价的业务 readiness 检测。
- `/health` 只返回固定状态，未检测 MySQL、模型配置、权重或文件系统。
- 网关有 200 MB 请求体限制，但后端直连路径没有同样的应用级限额。
- 网关未显式关闭流代理缓冲、设置长分析请求的读超时或心跳策略，应进行实际代理流测试。
- 当前配置未实现 TLS 终止、流量限制、独立数据库业务账号、GPU 资源声明或任务 Worker 隔离。
- 后端 Dockerfile 未显式安装 OpenCV 可能需要的系统运行库；Linux 镜像能否导入 cv2 需在镜像构建/启动验证，不能用本机成功替代。
- backend 的 Docker ignore 不排除 `.env*`，`COPY . .` 会把构建上下文中的环境文件带进镜像。frontend 也没有排除 `.env*`；其多阶段构建最终只拷贝 dist，但配置仍进入构建阶段。真实密钥不应写入版本库或构建上下文。

## 12. 已确认问题与优先级

优先级是本次工程判断，不是漏洞评分。以下区分源码确认、离线复现与尚待运行验证。

### 12.1 上线前优先处理

| 问题 | 证据 | 影响与建议 |
| --- | --- | --- |
| 上传资源未鉴权公开访问 | [main.py:48](/Users/jeremyyang/Project/Safescan_agent/backend/main.py:48) | 整体静态挂载；拿到 URL 即可访问，UUID 目录不是权限控制。改为资源归属校验后的下载，或受控短时链接 |
| 密码为无盐 MD5 | [db.py:277](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:277) | 密码存储强度不足；升级为专用密码哈希并设计旧密码迁移，字段宽度也须调整 |
| token/公开 ID 有内置默认密钥 | [auth.py:13](/Users/jeremyyang/Project/Safescan_agent/backend/app/auth.py:13)、[public_ids.py:28](/Users/jeremyyang/Project/Safescan_agent/backend/app/utils/public_ids.py:28) | 生产缺配置应拒绝启动；不应静默回退 |
| 空 API base 回退到 8000 | [App.jsx:59](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:59) | 离线函数复现：页面在 8080 时空值生成 host:8000，而 prod 未公开该端口。应以同源为默认，且核对根 .env 覆盖 |
| 当前本地 OpenAI 客户端无法初始化 | requirements 与本地 metadata；离线构造复现 | 本地 openai 1.3.7 + httpx 0.28.1 报 `unexpected keyword argument 'proxies'`。requirements 实际固定 httpx 0.25.0；先消除本地漂移，再锁定/验证完整依赖组合 |
| 最新 PDF 返回公开 ID，但下载接口接收 int | [report.py:508](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/report.py:508)、[report.py:517](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/report.py:517) | 生成后的即时链接使用内部整数；重新读取 latest 得到 q5_ 公开 ID，和 int 参数不匹配，预期返回 422。统一公开 ID 解析入口 |

鉴权 token 为 `Base64URL(payload).HMAC-SHA256` 两段自定义格式，**不是标准 JWT**。目前没有刷新 token、服务端注销/吊销、登录节流或密码重置实现；前端退出仅清理本地状态。

### 12.2 AI 工作流正确性与可靠性

| 问题 | 证据 | 精确影响 |
| --- | --- | --- |
| async 编排内调用同步 Writer | [agent_team.py:322](/Users/jeremyyang/Project/Safescan_agent/backend/app/workflow/agent_team.py:322)、[autogen_agent_base.py:93](/Users/jeremyyang/Project/Safescan_agent/backend/app/agents/autogen_agent_base.py:93) | Writer 的同步路径拒绝正在运行的事件循环；错误被转成 error 字典。外层 asyncio.run 结束后还有同步兜底，因此并非所有报告必然失败，但正常路径依赖异常兜底 |
| PDF repair 同样位于 async 接口内 | [report.py:438](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/report.py:438)、[report_pdf_agent.py:16](/Users/jeremyyang/Project/Safescan_agent/backend/app/agents/report_pdf_agent.py:16) | 同步调用错误被吞并返回 None，PDF 仍可按原报告渲染，但宣称的 L1 修复步骤可能实际未执行 |
| 先占用会话再验证视频路径 | [report.py:188](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/report.py:188) | 路径校验失败发生于 worker 启动前，而释放在 worker finally；会话会保持进程内占用，后续返回 409，直到进程重启等状态重置 |
| 校验失败仍可 complete | [report.py:303](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/report.py:303) | success 未作为保存/成功响应的门槛；用户可能看到不合格报告 |
| 存库异常仍可能 complete | [report.py:380](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/report.py:380) | UI 当下显示成功，刷新后数据缺失；需要把生成、校验、持久化成功分别建模 |
| 空证据也发送 complete | [report.py:235](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/report.py:235)、[App.jsx:1555](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:1555) | 前端把 complete 当作已有报告并锁定，实际可能只有 warning、没有落库报告 |
| 场景默认并发被压到 1 | [scene_agent.py:38](/Users/jeremyyang/Project/Safescan_agent/backend/app/agents/scene_agent.py:38) | 将 AGENT_MAX_CONCURRENCY 设置成 5 并不会得到默认 5 路视觉并发 |
| 任务没有持久化队列 | [report.py:403](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/report.py:403) | 后端重启会丢任务；多进程不共享锁；没有恢复、取消、统一并发和资源配额 |

### 12.3 功能、维护性和运行风险

- PDF 只上传不抽取正文，报告比较功能对外部 PDF 的能力不完整。
- async 聊天直接阻塞调用外部 SDK/重试休眠，影响同进程其他请求。
- 每次分析实例化 WorkflowOrchestrator 并加载 YOLO 权重；重复加载和多任务内存成本需要测量。
- 前端/后端物理路径耦合，自定义 OUTPUT_DIR 可能破坏图片 URL。
- 请求中重复 DDL、缺少显式事务、email 无唯一约束，影响一致性与并发。
- video 上传几乎只要求 filename，未做内容解码前的类型白名单、时长/分辨率/应用级大小限制；网关 200 MB 限制不能覆盖后端直连。
- 模型异常和 trace 会输出图片路径、部分原始模型响应；未见结构化日志脱敏和持久审计方案。
- 前端 localStorage token 受页面脚本可读，需结合 XSS 防护和会话策略审视；DOMPurify 已提供部分内容渲染防护，但不等于全站无 XSS 风险。
- 权重二进制直接 Git 跟踪，未见 LFS/模型版本元数据；后端依赖多数只有下界，无完整 lockfile。
- `backend/autogen.py` 是同名包导入代理，不是业务入口；部分 Agent 方法 return 后保留不可达旧 SDK 代码，增加理解成本。
- `guide._score()` 尚为 NotImplementedError，但当前检索使用 `_search_sections`，不能把这个未调用占位函数当成指南主链路故障。

## 13. 离线验证结果

| 检查 | 结果 | 能证明什么 / 不能证明什么 |
| --- | --- | --- |
| Git 初始状态 | 干净，main@79bf95f | 明确源码基线 |
| 41 个 Python 源文件 AST 解析 | 全部通过 | 语法有效；不代表导入/数据库/模型运行正常 |
| 前端 production build | 通过，47 modules | 当前本地 Node/依赖能打包；没有验证浏览器交互和后端连接 |
| 前端 ESLint | 5 errors、1 warning | 当前静态质量门禁不通过 |
| 本地 `pip check` | 通过 | 元数据声明满足；不保证实际 API 兼容 |
| OpenAI 构造，无网络请求 | TypeError: proxies | 证实当前本地 SDK 组合存在运行时不兼容 |
| 抽取原 `_run_agent_sync` 在事件循环内执行 | 复现 RuntimeError | 验证同步/异步边界；不冒充完整云模型 E2E |
| 抽取原 resolveApiBase，模拟 8080 页面 | 空配置返回 8000 | 证实生产默认地址逻辑的条件性错误 |
| Git 跟踪测试源码检索 | 0 | 本地缓存不算可执行、可维护测试集 |

ESLint 具体输出：App.jsx 三个未使用状态变量和一个 useEffect 依赖警告；Profile.jsx 的 effect 内同步 setState；ThreadContent.jsx 的未使用 pdfStatusText。

构建输出位于独立临时目录，没有覆盖已有前端 dist：[本次离线构建目录](/private/tmp/safescan-analysis-SHzMz7/frontend-dist)。主 JS 331.22 kB，gzip 103.78 kB；CSS 24.44 kB，gzip 5.17 kB。这些是本次构建观测值，不是性能测试结果。

本地 backend/.venv 的部分实装版本：FastAPI 0.129.0、Uvicorn 0.41.0、Pydantic 2.12.5、pyautogen 0.10.0、autogen-agentchat/core 0.7.5、OpenAI 1.3.7、httpx 0.28.1、Ultralytics 8.4.14、PyTorch 2.10.0、ReportLab 4.4.10。它们不是部署承诺；尤其 httpx 偏离 requirements。

未执行：真实登录/数据库检查、视频分析、付费模型请求、PDF 实际渲染验收、Docker 镜像构建/启动、浏览器 E2E、迁移脚本或负载测试。本文涉及这些环境行为的风险，不应被解读成已经完成线上复现。

## 14. 建议演进顺序

### 第一阶段：修正当前契约和安全边界

1. 私有化上传文件访问，统一 file_id → 受控 URL/下载流程。
2. 改进密码哈希和密钥必填校验，审核版本库/镜像中的环境文件。
3. 修正 production API base 和 PDF public ID 下载契约。
4. 对齐本地与声明依赖，固定 AutoGen/OpenAI/httpx 的实际可用组合。
5. 统一同步/异步 Agent 调用方式，修复任务占用释放和错误传播。
6. 对报告校验、持久化成功、无有效证据分别返回明确状态。

### 第二阶段：建立可回归的工程基础

1. 补齐鉴权/资源归属、ID 编码、文件路径、报告校验、下载及流事件测试。
2. 视频/LLM 测试用固定样本和 mock provider，避免常规 CI 消耗云模型额度。
3. 将 schema 迁移移出请求路径，为多表写入建立事务边界和数据库约束。
4. 拆分 App 的请求层/业务 Hooks，以及 db.py 的 repositories/migrations。
5. 明确 PDF 上传到底是附件管理还是正文问答，若是后者再实现解析/OCR、来源标注与上下文限制。
6. 增加服务 readiness、结构化日志、任务 ID、耗时/失败率/模型 token 成本记录。

### 第三阶段：在负载需求明确后扩展

将视频任务迁移到独立 Worker 和持久队列；统一任务状态与恢复策略；共享私有对象存储；配置模型实例复用、CPU/GPU 和并发配额；对代表图选择、云模型准确性、视频时长上限和费用开展量化评估。

不建议仅因本地 .env 已出现 PostgreSQL/Redis/MinIO 就立即重写现有架构。应先验证业务目标与当前缺陷，再决定是否迁移基础设施。

## 15. 数据迁移路径与操作注意

历史升级顺序在 README 中分为：用户 UUID 文件目录隔离 → 报告存储 V2 → 稳定后删除旧列。

| 文件 | 用途 | 注意 |
| --- | --- | --- |
| [migrate_uploads_to_user_storage.py](/Users/jeremyyang/Project/Safescan_agent/backend/scripts/migrate_uploads_to_user_storage.py) | 旧视频/PDF/图片目录迁入用户空间，更新路径 | 默认 dry-run 仍调用 `_ensure_core_tables`，可能建表/回填 UUID；不要当作严格只读 |
| [migrate_reports_storage_v2.py](/Users/jeremyyang/Project/Safescan_agent/backend/scripts/migrate_reports_storage_v2.py) | 旧 reports 数据迁入 files 和类型子表 | 有 apply 控制；迁移前先备份并检查旧库形态 |
| [drop_legacy_report_columns.py](/Users/jeremyyang/Project/Safescan_agent/backend/scripts/drop_legacy_report_columns.py) | 删除旧报告字段 | 不可作为普通启动步骤；谨慎使用 force |
| [迁移执行清单](/Users/jeremyyang/Project/Safescan_agent/backend/docs/report_storage_refactor_rollout.md) | 分阶段迁移说明 | 要与实际代码和备份/回滚方案一起使用 |

本次没有执行任何迁移或删除动作。

## 16. 总结

当前项目的核心价值在于把本地视觉预处理、云端多模态分析、受控多角色报告生成、会话问答与持久化串成一个产品闭环。技术复杂度主要位于 AI 调用边界、长任务生命周期、报告数据契约和文件权限，而不在前端框架选型。

后续应优先保证“配置能一致启动、成功状态可信、文件只能由所有者访问、数据可回归验证”，再推进队列化和存储扩展。分析过程中参考 backend-patterns 的分层、事务、并发与可观测性检查思路；未据此改动源码，也未把其中的 Node.js/Next.js 示例误套成当前项目技术栈。
