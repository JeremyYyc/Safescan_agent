# Safe Scan Agent：目录、入口与功能路径索引

基线：2026-08-31，`main@79bf95f`。

> 历史基线文件。五阶段重构后的实际路径请阅读 [当前架构与路径索引](ARCHITECTURE.zh-CN.md)。

项目根目录：`/Users/jeremyyang/Project/Safescan_agent`。

配套阅读：[详细技术分析](/Users/jeremyyang/Project/Safescan_agent/docs/TECHNICAL_ANALYSIS.zh-CN.md)。本文件负责“去哪里找”，技术判断、已确认问题及验证边界见分析文档。

## 1. 目录总览

以下为源码目录结构，生成物和本地运行数据单独列出。

```text
Safescan_agent/
├── README.md
├── .gitignore
├── docker-compose.yml
├── docker-compose.test.yml
├── docker-compose.prod.yml
├── package-lock.json                  根目录小型锁文件，非前端依赖入口
├── backend/
│   ├── main.py                        FastAPI 应用入口
│   ├── autogen.py                     同名包导入代理，非业务入口
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── .env.test
│   ├── .env.production
│   ├── app/
│   │   ├── __init__.py
│   │   ├── auth.py                    token / 用户鉴权依赖
│   │   ├── db.py                      MySQL 数据访问与 schema 兼容
│   │   ├── env.py                     后端环境加载
│   │   ├── llm_registry.py            分层模型配置
│   │   ├── yolov8m.pt                 本地目标检测权重
│   │   ├── api/                       五组 HTTP 路由
│   │   ├── agents/                    模型角色与 AutoGen 适配
│   │   ├── workflow/                  工作流、状态、修复循环
│   │   ├── tools/                     视频工具和规则校验
│   │   ├── prompts/                   报告与聊天 Prompt
│   │   ├── knowledge/                 产品指南 JSON 和检索
│   │   ├── pdf/                       PDF 排版
│   │   └── utils/                     UUID / 公开 ID
│   ├── scripts/                       三个历史迁移/清理脚本
│   └── docs/                          报告存储迁移清单
├── frontend/
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.js
│   ├── eslint.config.js
│   ├── index.html
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── .dockerignore
│   ├── .gitignore
│   ├── .env.test
│   ├── .env.production
│   ├── README.md
│   ├── public/                        品牌图、首页图、Vite 模板资源
│   └── src/
│       ├── main.jsx                   React 入口
│       ├── App.jsx                    状态/请求/路由主控制器
│       ├── index.css
│       ├── App.css
│       ├── assets/react.svg
│       ├── layouts/ChatLayout.jsx
│       ├── pages/                     登录/资料/聊天/报告页面
│       └── styles/                    auth / home / profile CSS
├── gateway/
│   ├── Dockerfile
│   └── nginx.conf
└── docs/                              本次新增分析文档
    ├── TECHNICAL_ANALYSIS.zh-CN.md
    └── PATH_INDEX.zh-CN.md
```

本地还有根 `.env`、两套 Python venv、测试缓存、前端 node_modules/dist、后端 uploads 等内容。其中根 `.env` 不被后端加载器自动读取；tests 与 backend/tests 在本次检查时只有 `__pycache__`，没有已跟踪测试源码。

## 2. 建议阅读顺序

1. [README](/Users/jeremyyang/Project/Safescan_agent/README.md)：理解产品目标与运行方式，但用源码校正文档差异。
2. [前端依赖](/Users/jeremyyang/Project/Safescan_agent/frontend/package.json)、[后端依赖](/Users/jeremyyang/Project/Safescan_agent/backend/requirements.txt)：确定技术栈。
3. [main.py](/Users/jeremyyang/Project/Safescan_agent/backend/main.py)、[App.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx)：理解前后端入口。
4. [report API](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/report.py)、[orchestrator](/Users/jeremyyang/Project/Safescan_agent/backend/app/workflow/orchestrator.py)：顺着视频主链阅读。
5. [agent_team](/Users/jeremyyang/Project/Safescan_agent/backend/app/workflow/agent_team.py)、[模型基类](/Users/jeremyyang/Project/Safescan_agent/backend/app/agents/autogen_agent_base.py)：理解 AI 角色、调用协议与并发。
6. [db.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py)：理解报告、会话、文件关联。
7. [Compose](/Users/jeremyyang/Project/Safescan_agent/docker-compose.yml)、[网关](/Users/jeremyyang/Project/Safescan_agent/gateway/nginx.conf)：理解容器网络和访问入口。

## 3. 前端源码索引

| 路径 | 作用 | 修改时关注 |
| --- | --- | --- |
| [src/main.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/main.jsx) | createRoot、StrictMode、BrowserRouter | React 总入口 |
| [src/App.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx) | 路由、状态、API、上传、报告和聊天 | 变化影响面最大 |
| [layouts/ChatLayout.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/layouts/ChatLayout.jsx) | 侧栏、菜单、会话搜索、报告引用和弹层 | 大量 props 和 Outlet context |
| [pages/ThreadContent.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/pages/ThreadContent.jsx) | 报告/消息正文、表格、图片、Markdown | 报告结构兼容和 HTML 清洗 |
| [pages/ChatIndexPage.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/pages/ChatIndexPage.jsx) | 聊天入口初始化 | 调用 handleGoHome |
| [pages/ChatThreadPage.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/pages/ChatThreadPage.jsx) | 按 threadId 加载会话 | 路由参数与重复加载保护 |
| [pages/ReportNewPage.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/pages/ReportNewPage.jsx) | 新报告草稿初始化 | 调用 handleNewChat |
| [pages/ReportThreadPage.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/pages/ReportThreadPage.jsx) | 报告详情路由 | 请求序号保护、404 跳转 |
| [pages/Login.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/pages/Login.jsx) | 登录表单 | 提交逻辑在 App |
| [pages/Register.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/pages/Register.jsx) | 注册表单 | 表单字段与后端 DTO |
| [pages/Profile.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/pages/Profile.jsx) | 用户资料 | 用户名状态同步和保存 |
| [src/index.css](/Users/jeremyyang/Project/Safescan_agent/frontend/src/index.css) | 全局基础样式 | 全局视觉影响 |
| [src/App.css](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.css) | 少量 App 样式 | 注意是否被实际引用 |
| [styles/home.css](/Users/jeremyyang/Project/Safescan_agent/frontend/src/styles/home.css) | 主界面样式 | 最大样式文件，含布局与响应式 |
| [styles/auth.css](/Users/jeremyyang/Project/Safescan_agent/frontend/src/styles/auth.css) | 登录注册样式 | 认证页面 |
| [styles/profile.css](/Users/jeremyyang/Project/Safescan_agent/frontend/src/styles/profile.css) | 资料页样式 | 个人资料页面 |

### App.jsx 功能定位

| 功能 | 起始位置 |
| --- | --- |
| API base 推导 | [resolveApiBase](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:59) |
| token / 用户信息持久化 | [persistAuth](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:346) |
| Bearer 请求封装 | [apiFetch](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:377) |
| 获取/生成/预览/下载 PDF | [loadLatestPdfForChat](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:433) |
| 会话与报告搜索 | [fetchChats](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:617) |
| 历史消息加载 | [loadChatMessages](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:706) |
| 登录注册 | [handleLogin](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:811) |
| 引用报告与比较 | [handleAddReportRef](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:1006) |
| 上传 PDF | [handleUploadPdfReport](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:1136) |
| 重命名、置顶、删除 | [handleRenameChat](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:1199) |
| 文件路径转图片 URL | [toUploadUrl](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:1310) |
| 视频上传与 NDJSON 消费 | [handleRunAnalysis](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:1465) |
| 普通聊天与打字效果 | [handleChat](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:1582) |
| 浏览器路由树 | [Routes](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx:1677) |

## 4. 后端基础与数据层索引

| 路径 | 职责 |
| --- | --- |
| [main.py](/Users/jeremyyang/Project/Safescan_agent/backend/main.py) | create_app、CORS、路由注册、StaticFiles、health |
| [app/env.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/env.py) | app/.env 与 backend/.env 加载优先级 |
| [app/auth.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/auth.py) | 创建/验证自定义 HMAC token，require_user |
| [app/llm_registry.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/llm_registry.py) | L1/L2/L3/VL 模型名、temperature/top_p、并发读取 |
| [app/db.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py) | 所有 MySQL 数据访问与请求内 schema 修补 |
| [app/utils/public_ids.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/utils/public_ids.py) | 用户/会话/报告公开 ID 编解码 |
| [app/utils/uuid7.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/utils/uuid7.py) | uuid6 调用和兼容生成逻辑 |
| [autogen.py](/Users/jeremyyang/Project/Safescan_agent/backend/autogen.py) | 防止同名模块遮蔽外部包的导入代理 |

### db.py 内部导航

| 起点 | 模块 |
| --- | --- |
| [62](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:62) | DATABASE_URL 解析、连接、可用性检查 |
| [116](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:116) | users/chats/messages/chat_details 建表与兼容 |
| [277](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:277) | 密码、用户查询、注册、storage_uuid |
| [416](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:416) | 会话 CRUD、公开 ID 解析、列表 |
| [657](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:657) | 消息、报告明细、报告引用写入 |
| [837](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:837) | 文件路径标准化、哈希、批量资产读取 |
| [917](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:917) | 报告主/子表 join、统一历史数据返回 |
| [1078](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:1078) | 文件登记与 report_assets 维护 |
| [1168](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:1168) | bot 聊天活跃引用的模型上下文 |
| [1227](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:1227) | 最新报告、最新 PDF、报告 ID 与搜索 |
| [1501](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:1501) | PDF 写入与删除 |
| [1592](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:1592) | 会话历史、近期问题、区域信息读取 |
| [1752](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:1752) | reports/files/report_analysis/report_pdf/report_assets DDL |
| [1969](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:1969) | chat_report_refs DDL |
| [2017](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py:2017) | 分析报告写入 |

## 5. AI、视觉、知识与 PDF 路径

| 路径 | 职责 | 接入关系 |
| --- | --- | --- |
| [workflow/orchestrator.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/workflow/orchestrator.py) | 视频到 AI 草稿的主编排 | report worker 调用 |
| [workflow/state.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/workflow/state.py) | WorkflowState dataclass、trace/listeners、序列化 | orchestrator 和流响应共享 |
| [workflow/agent_team.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/workflow/agent_team.py) | 角色计划、启发式兜底、阶段并行和 Writer | 主流程实际使用的多角色团队 |
| [workflow/react_loop.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/workflow/react_loop.py) | 规则校验失败后的重写循环 | API worker 在草稿生成后调用 |
| [agents/autogen_agent_base.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/agents/autogen_agent_base.py) | AssistantAgent、同步/异步调用、多模态消息、JSON 解析 | AutoGen 模型角色基类 |
| [agents/dashscope_client.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/agents/dashscope_client.py) | AutoGen ChatCompletionClient → OpenAI-compatible API | 协议适配、usage 和图像转换 |
| [agents/base_agent.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/agents/base_agent.py) | 旧式基础 Agent/响应解析辅助 | Validator 使用，不等同 AutoGen 基类 |
| [agents/scene_agent.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/agents/scene_agent.py) | VL 看图、重试、解析、房间分组、YOLO fallback | 图像证据提取 |
| [agents/router_agent.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/agents/router_agent.py) | L1 返回角色列表 | 可失败并退回启发式计划 |
| [agents/report_writer_agent.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/agents/report_writer_agent.py) | L3 合并证据与风险，生成/归一化报告 | 首次报告与修复循环复用 |
| [agents/validator_agent.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/agents/validator_agent.py) | 封装规则校验 | 不调用云模型验证事实 |
| [agents/title_agent.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/agents/title_agent.py) | L2 生成英文短标题 | 报告生成后更新默认会话标题 |
| [agents/report_pdf_agent.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/agents/report_pdf_agent.py) | L1 修复 PDF 前的报告 JSON | 有同步/异步边界问题，见技术分析 |
| [tools/video_tools.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/tools/video_tools.py) | 抽帧、去重、过滤、场景分段、代表图、YOLO | 不负责 LLM 推理 |
| [tools/validation_tools.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/tools/validation_tools.py) | 报告字段、区域分数、建议结构检查 | Validator 的确定性工具 |
| [prompts/report_prompts.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/prompts/report_prompts.py) | 所有报告角色 Prompt 和输出格式 | 修改报告字段时同步检查验证器、UI、PDF |
| [prompts/chat_prompts.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/prompts/chat_prompts.py) | 意图分类、聊天约束与系统提示 | processChat 使用 |
| [knowledge/quick_guide.json](/Users/jeremyyang/Project/Safescan_agent/backend/app/knowledge/quick_guide.json) | 产品使用说明内容 | UI 指南与聊天检索共用 |
| [knowledge/guide.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/knowledge/guide.py) | 内容加载缓存、分词、BM25 风格检索 | 非向量检索 |
| [pdf/report_pdf.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/pdf/report_pdf.py) | ReportLab 文本/表格/卡片排版 | export-pdf 调用 |
| [yolov8m.pt](/Users/jeremyyang/Project/Safescan_agent/backend/app/yolov8m.pt) | YOLO 权重二进制 | orchestrator 初始化时加载 |

各包的 `__init__.py` 主要是包标记，不是独立业务模块。不存在独立 HazardAgent.py、ComfortAgent.py 等文件，这些角色逻辑位于 agent_team.py 和 report_prompts.py。

## 6. API 路径全表

以下 21 条是源码中注册的业务 API；除登录/注册外均使用 require_user。具体资源操作仍需检查对应函数的 ownership 校验。

| 方法 | HTTP 路径 | 用途 | 源码 |
| --- | --- | --- | --- |
| POST | `/api/auth/login` | 登录、返回 token/user | [auth.py:52](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/auth.py:52) |
| POST | `/api/auth/register` | 注册并登录 | [auth.py:62](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/auth.py:62) |
| PUT | `/api/auth/profile` | 修改用户名 | [auth.py:75](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/auth.py:75) |
| POST | `/api/processChat` | 意图识别和聊天回答 | [chat.py:345](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/chat.py:345) |
| GET | `/api/guide` | 产品指南章节 | [guide.py:10](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/guide.py:10) |
| POST | `/api/reports/upload-pdf` | 保存上传 PDF | [history.py:240](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/history.py:240) |
| POST | `/api/chats` | 新建 report/bot 会话 | [history.py:301](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/history.py:301) |
| GET | `/api/chats` | 分页会话列表 | [history.py:324](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/history.py:324) |
| GET | `/api/reports/search` | 搜索报告 | [history.py:336](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/history.py:336) |
| GET | `/api/chats/{chat_id}/messages` | 历史消息与报告上下文 | [history.py:358](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/history.py:358) |
| PUT | `/api/chats/{chat_id}` | 标题、类型、置顶等元信息 | [history.py:395](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/history.py:395) |
| DELETE | `/api/chats/{chat_id}` | 删除会话并尝试回收资产 | [history.py:425](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/history.py:425) |
| POST | `/api/chats/{chat_id}/messages` | 保存消息 | [history.py:440](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/history.py:440) |
| GET | `/api/chats/{chat_id}/report-refs` | 获取报告引用 | [history.py:469](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/history.py:469) |
| POST | `/api/chats/{chat_id}/report-refs` | 添加报告/源会话引用 | [history.py:513](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/history.py:513) |
| DELETE | `/api/chats/{chat_id}/report-refs/{report_id}` | 移除引用；选项控制删除 PDF 源 | [history.py:564](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/history.py:564) |
| POST | `/api/uploadVideo` | 上传视频，返回磁盘路径 | [report.py:141](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/report.py:141) |
| POST | `/api/processVideoStream` | 分析视频并返回 NDJSON | [report.py:169](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/report.py:169) |
| POST | `/api/reports/{chat_id}/export-pdf` | 导出当前报告 PDF | [report.py:418](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/report.py:418) |
| GET | `/api/reports/{chat_id}/pdf-latest` | 获取最近 PDF 链接 | [report.py:482](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/report.py:482) |
| GET | `/api/reports/pdf/{report_id}/download` | 文件下载，当前参数类型为 int | [report.py:515](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/report.py:515) |

额外入口：

- `/health`：公开、固定 liveness 响应。
- `/health/auth`：需要鉴权，返回用户 ID。
- `/uploads/...`：公开静态资源入口，与 API ownership 检查不是同一个访问边界。
- `/docs`、`/redoc`、`/openapi.json`：FastAPI 默认直接后端入口；生产网关没有单独将这些路径转给后端，不能假设网关地址上同样可访问。

接口风格混合了 REST 资源名与 `uploadVideo/processChat` 动词路径。`/reports/{chat_id}` 的参数实际上是会话标识，不是报告标识；维护时务必区分。

### 关键请求与响应

| 接口 | 输入重点 | 输出重点 |
| --- | --- | --- |
| uploadVideo | multipart `file` | `video_path`、`filename` |
| processVideoStream | `video_path`、`attributes`、`chat_id` | 每行 JSON；type 为 trace / complete / error / end |
| processChat | `chat_id`、`message`；另有兼容输入 | 完整 JSON `{reply}`，非 token 流 |
| chats POST | `title`、`chat_type`（report/bot） | `{chat}` |
| reports/search | `q`、`limit`、`offset` | `{keyword, items}` |
| report-refs POST | `report_id` 或 `source_chat_id` | 添加结果、报告公开 ID |
| export-pdf | 会话 ID | report_id、pdf_url、download_url |
| pdf-latest | 会话 ID | `{pdf: null}` 或 PDF 元数据 |

视频 complete 的常规结果含 `regionInfo`、`report`、`representativeImages`、`video_path`、`workflowLog`。空证据分支与成功分支结构不完全一致，消费者不能只凭 complete 认定报告有效。

## 7. 配置、部署与迁移文件索引

| 文件 | 职责 |
| --- | --- |
| [docker-compose.yml](/Users/jeremyyang/Project/Safescan_agent/docker-compose.yml) | 四服务、数据库健康检查、命名卷 |
| [docker-compose.test.yml](/Users/jeremyyang/Project/Safescan_agent/docker-compose.test.yml) | 测试 env_file、宿主端口 5173/8000/3307，禁用默认网关 |
| [docker-compose.prod.yml](/Users/jeremyyang/Project/Safescan_agent/docker-compose.prod.yml) | 生产 env_file、restart、网关 8080 |
| [backend/Dockerfile](/Users/jeremyyang/Project/Safescan_agent/backend/Dockerfile) | Python 3.11 + pip + Uvicorn |
| [backend/.dockerignore](/Users/jeremyyang/Project/Safescan_agent/backend/.dockerignore) | 排除上传、缓存、脚本和迁移说明等；未排除 .env |
| [frontend/Dockerfile](/Users/jeremyyang/Project/Safescan_agent/frontend/Dockerfile) | Node 构建 → Nginx 运行的多阶段镜像 |
| [frontend/nginx.conf](/Users/jeremyyang/Project/Safescan_agent/frontend/nginx.conf) | 静态文件服务、SPA 路由回退 |
| [gateway/Dockerfile](/Users/jeremyyang/Project/Safescan_agent/gateway/Dockerfile) | 网关 Nginx 镜像 |
| [gateway/nginx.conf](/Users/jeremyyang/Project/Safescan_agent/gateway/nginx.conf) | /api、/uploads、/health、前端反向代理 |
| [frontend/vite.config.js](/Users/jeremyyang/Project/Safescan_agent/frontend/vite.config.js) | React 插件；未设置 dev proxy |
| [frontend/eslint.config.js](/Users/jeremyyang/Project/Safescan_agent/frontend/eslint.config.js) | ESLint flat config 和 Hooks 规则 |
| [backend/.env.test](/Users/jeremyyang/Project/Safescan_agent/backend/.env.test) | 后端测试配置；本文不展示值 |
| [backend/.env.production](/Users/jeremyyang/Project/Safescan_agent/backend/.env.production) | 后端生产配置；本文不展示值 |
| [frontend/.env.test](/Users/jeremyyang/Project/Safescan_agent/frontend/.env.test) | 前端 test mode API base |
| [frontend/.env.production](/Users/jeremyyang/Project/Safescan_agent/frontend/.env.production) | 前端 production mode API base |
| [.gitignore](/Users/jeremyyang/Project/Safescan_agent/.gitignore) | 环境/运行目录排除规则；显式允许 test/production 环境文件 |
| [迁移：用户存储目录](/Users/jeremyyang/Project/Safescan_agent/backend/scripts/migrate_uploads_to_user_storage.py) | 历史文件按 storage_uuid 迁移，重写路径 |
| [迁移：报告 V2](/Users/jeremyyang/Project/Safescan_agent/backend/scripts/migrate_reports_storage_v2.py) | reports 旧结构迁往类型子表和 files |
| [清理：旧报告列](/Users/jeremyyang/Project/Safescan_agent/backend/scripts/drop_legacy_report_columns.py) | 稳定后移除旧字段 |
| [迁移执行清单](/Users/jeremyyang/Project/Safescan_agent/backend/docs/report_storage_refactor_rollout.md) | 迁移顺序与核对事项 |

环境文件链接用于定位，不表示适合分享文件内容。不要把密钥粘贴进分析文档、日志或工单。

## 8. 按需求找修改点

| 想做的事情 | 推荐起点 | 必须一起核对 |
| --- | --- | --- |
| 更改云模型 | [llm_registry.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/llm_registry.py) | 后端 env、AutoGen adapter、原生 DashScope 聊天两条链 |
| 改抽帧频率或代表图数量 | [orchestrator.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/workflow/orchestrator.py) | video_tools、云模型请求量、漏检与耗时 |
| 调整危险识别/评分 Prompt | [report_prompts.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/prompts/report_prompts.py) | agent_team、输出校验、评估样例 |
| 新增报告字段 | [report_writer_agent.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/agents/report_writer_agent.py) | Prompt → validation_tools → JSON 存储 → ThreadContent → PDF |
| 新增用户人群标签 | [App.jsx](/Users/jeremyyang/Project/Safescan_agent/frontend/src/App.jsx) | ChatLayout/ThreadContent 表单、agent_team 属性映射、Prompt |
| 更改聊天策略 | [api/chat.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/chat.py) | chat_prompts、消息 meta、指南检索 |
| 更新产品指南 | [quick_guide.json](/Users/jeremyyang/Project/Safescan_agent/backend/app/knowledge/quick_guide.json) | API 和聊天检索共用，进程缓存刷新 |
| 支持读取上传 PDF 内容 | [history.py:240](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/history.py:240) | 新解析链、report_pdf preview、上下文预算和文件安全 |
| 改 PDF 排版 | [report_pdf.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/pdf/report_pdf.py) | 字体、长表分页、报告字段、实际渲染验收 |
| 修复 PDF 下载链接 | [report.py:482](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/report.py:482) | latest / export / download 三处 ID 契约、前端缓存 |
| 改存储目录/对象存储 | [report.py:35](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/report.py:35) | history 清理、files 表、main 静态挂载、前端 toUploadUrl、迁移脚本 |
| 改鉴权 | [auth.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/auth.py) | API ownership、密码存储、localStorage、静态资源访问 |
| 分离 Worker 或限制并发 | [report.py:169](/Users/jeremyyang/Project/Safescan_agent/backend/app/api/report.py:169) | 持久任务状态、取消恢复、共享文件、模型生命周期、流事件 |
| 改数据库表结构 | [db.py](/Users/jeremyyang/Project/Safescan_agent/backend/app/db.py) | 请求内 DDL、历史迁移、旧字段兼容、事务和索引 |
| 修改部署域名/端口 | [prod Compose](/Users/jeremyyang/Project/Safescan_agent/docker-compose.prod.yml) | 网关、构建期 VITE_API_BASE、CORS、根 .env 插值 |

## 9. 接手项目时的注意事项

1. 先区分 report 会话、bot 会话、analysis 报告、pdf 报告，避免把会话 ID 和报告 ID 混用。
2. 区分数据库整数 ID、公开 ID、storage_uuid、文件 UUID；名称相似不代表可互换。
3. 区分代码目录、运行磁盘路径和 HTTP URL；前端不应长期依赖服务器绝对路径。
4. 不要直接导入/调用业务 DB 查询当“只读诊断”，很多函数会自动执行 schema 维护。
5. 用户目录迁移脚本的 dry-run 不是严格零写入；运行前阅读分析文档的迁移注意事项。
6. 不要把根目录 PostgreSQL/Redis/MinIO 配置误认为当前架构已切换。
7. 不要用存在测试缓存、本机已安装依赖或健康检查成功替代完整测试与部署验收。

本文档只整理路径，没有进行代码重构、目录搬迁、数据库变更或文件删除。
