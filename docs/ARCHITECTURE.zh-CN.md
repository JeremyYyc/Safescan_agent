# 重构后技术栈、架构与路径索引

日期：2026-08-31。集成分支：`refactor/plan`。本文描述五阶段重构后的源码；原技术分析和路径索引保留为 `main@79bf95f` 的历史基线，不代表当前实现。

后续网关改造已统一前端/API 与 MinIO 的 Nginx 入口，移除 CORS/前端 API 地址配置；入口、网络和未来 Redis/worker 扩展见 [Nginx 网关](NGINX_GATEWAY.zh-CN.md)。

## 1. 模块与技术边界

| 层 | 实现 | 主要职责 |
|---|---|---|
| UI | React 19 / Vite 7 / React Router 6 | 上传、NDJSON 进度、报告展示、引用问答、鉴权资源读取 |
| HTTP | FastAPI / Pydantic | token 鉴权、输入校验、资源所有权、流式响应 |
| Workflow | LangGraph 1.2.11 | typed state、条件边、并行汇合、有限修复循环 |
| 模型 | OpenAI SDK 2.54.0 / HTTPX 0.28.1 | Qwen compatible-mode、标准 tool calls、超时与客户端释放 |
| 工具 | Pydantic schema + 显式注册表 | 名称白名单、严格参数、可信身份、资源白名单、预算 |
| 数据 | PostgreSQL 17 / SQLAlchemy 2.0.48 / psycopg 3.3.4 | 连接池、领域仓储、事务、JSONB 与外键 |
| Schema | Alembic 1.18.4 | 0001 初始十表、0002 MinIO 文件元数据；请求路径无 DDL |
| 对象 | MinIO SDK 7.2.20 | 私有视频、派生图和 PDF；数据库仅保留元数据/引用 |
| 视觉 | 原 YOLOv8m / OpenCV / PyTorch / PyAV 16.1.0 | 内存解码、尺度归一化清晰度筛选、代表图选择、检测标注 |
| PDF | ReportLab | 内存渲染、MinIO 持久化、鉴权下载 |

没有 AutoGen 活跃依赖、MySQL 驱动调用、公开 uploads 静态目录或本地业务文件兼容层。`GraphModelAgent` 只是提示词/输出解析适配器，不是另一套 Agent 编排框架。

## 2. 图和状态

保留原上传与“Run Analysis”两步交互；上传图先持久化对象，返回 `video_asset_id`，主报告图以该稳定引用启动。每次分析由服务器分配 `run_id`；完成事件和节点完成 trace 带此 ID。没有跨 HTTP 请求挂起同一个运行中图，也没有 checkpoint/断点恢复承诺。

```text
上传图：receive → persist(MinIO + files 元数据) → END
                             │ video_asset_id
报告图：authorize → extract → filter → select → detect → scene → router
                     │空帧                    │空证据
                     └→ no_frames → END       └→ no_evidence → END
  router → [hazard || comfort/skip] → stage_two
         → [compliance/skip || scoring/skip] → recommendations/skip
         → write → (必要时 write_retry) → validate
                           ┌──────── repair ← 不合格
                           │轮次未满     │原终止条件
                           └→ validate   ↓
                       evidence → title → persist(PostgreSQL) → END

聊天图：load_context → classify → persist_user
       → guide / report / multi_report / smalltalk / safety / refusal
       → persist_answer → END

PDF 图：load → repair → render(BytesIO) → store(MinIO) → reference(PG) → END
模型图：model → tool calls? → tools → model；无工具调用则 END
```

两个角色阶段都有显式汇合边。可选角色节点返回空结果，不跳过必须到达的汇合点；Writer 只在依赖完成后运行一次（无 regions 时保留原额外写作重试）。

`WorkflowState` 存储身份、会话、资源引用、用户属性、筛选统计、代表图、YOLO 摘要、证据、角色计划/结果、草稿、校验轮次、标题、报告 ID 和 trace。并行节点写各自字段，trace 使用 reducer 合并。图片字节、数据库连接、模型对象和密钥不进入主报告状态；上传/PDF 子图短暂持有 bytes，存储节点清空，不 checkpoint。

同步仓储/视觉处理在线程执行，Qwen 调用异步；同步入口只在没有运行事件循环的线程中调用 `asyncio.run`。分析和上传各有进程内并发限制，角色节点受 `AGENT_MAX_CONCURRENCY` 限制。关闭流会请求取消，已开始的同步写操作不会伪装成立即停止。

## 3. 保留的报告逻辑与明确修复

- `app/prompts` 与 `main@79bf95f` 无差异；L1/L2/L3/VL 模型和采样参数不变。
- 保留按原帧索引间隔抽帧、pHash/清晰度/亮度/人脸筛选、直方图分段、代表图选择与 YOLO 检测规则。
- 零关键帧运行修正：清晰度在最长边 960 的等比例缩小图上测量，小图不放大，原证据分辨率不变；pHash 仅与上一张保留帧比较。阈值及原尺寸人脸检测不变；日志/trace 返回阶段帧数和剔除统计，无可用帧提前退出返回 error/end 而非成功报告。详见执行记录中的 keyframe-filter-fix。
- 保留角色选择、Hazard/Comfort 与 Compliance/Scoring 的依赖、Recommendation 汇总、证据匹配和标题逻辑。
- 保留原报告字段，包括 `regionName`、`evidenceImages`、评分数组及前端既有字段显示，不重新设计报告业务 schema。
- 保留“三次校验尝试，每次失败执行修复，最后一次修复不再校验”的行为。耗尽后仍可能保存报告，`validation.success` 保持 false；不是质量保证。
- 明确修复：同步/异步调用冲突；保存失败不再返回成功 complete；无效视频不占用处理锁；PDF 空 checklist；视频 raw body 前端集成遗漏；前端 lint 错误/警告。PDF 文件名按 UTF-8 安全编码。

## 4. 数据模型与持久化

| 表 | 责任 / 关系 |
|---|---|
| users | 归一化唯一 email、随机盐 scrypt、存储 UUID |
| chats | 用户会话、公开 UUID、类型/状态/置顶/更新时间 |
| messages | 消息文本、角色、JSONB meta |
| chat_details | 会话消息/报告时间线，约束恰好一种来源 |
| reports | 用户所有的 analysis/pdf 报告公共元信息 |
| report_analysis | 报告 JSONB、区域 JSONB、输入视频 file_id |
| report_pdf | PDF file_id、上传/导出类型、派生报告关系 |
| files | 私有 bucket/object_key、UUID、所有者、大小、MIME、SHA256 |
| report_assets | 报告与派生图片关联、排序、去重 |
| chat_report_refs | 聊天附加报告引用及 active/removed/deleted 状态 |

使用 bigint identity、原生 UUID、JSONB、带时区时间、唯一约束和外键索引；常用用户/时间线查询有组合索引。没有为小型 Demo 的全部 JSONB 字段盲目添加 GIN 索引。

仓储嵌套调用加入外层 UnitOfWork，外层统一提交/回滚；报告及关联、消息及明细原子提交。SQL 参数绑定，错误隐藏 SQL 参数。schema 由冻结的 Alembic 迁移管理。0002 遇到有历史本地文件记录的库会明确拒绝自动转换，不能当作旧库数据搬迁器。

MinIO 与 PostgreSQL 没有分布式事务：对象写入后元数据失败会补偿删除；媒体执行范围清理未引用的派生对象；删除通过引用检查和外键保护。清理失败记录日志和元数据，未实现持久化重试队列。对象删除成功但数据库提交失败等跨存储故障仍可能需要人工对账；不承诺 exactly-once。

## 5. 工具边界

注册的七个工具：`search_guide`、`read_report`、`validate_report`、`extract_video_frames`、`filter_video_frames`、`select_representative_images`、`detect_objects`。

- LLM 可见 JSON schema 不含用户身份、任意路径、SQL、bucket/key 或删除管理权限。
- 可信 `ToolContext` 注入用户/会话及资源白名单；报告工具只读当前会话或有效附件。
- 聊天 L2 可调用指南/报告读取；Writer/PDF repair 可调用校验。媒体节点确定性调用同一注册执行器，不让模型自由跳过必需阶段。
- 保留真实协议 `tools → assistant.tool_calls → role=tool/tool_call_id → model`。检查重复 ID、未知工具、额外字段、轮数、次数和输出预算。
- 只读调用支持超时；线程中的媒体写操作等待完成，依赖输入/执行限额，不使用不能停止线程的“伪取消”。

## 6. 当前路径索引

所有路径相对项目根目录。

| 路径 | 查找内容 |
|---|---|
| `.env.example` / `backend/app/settings.py` | 唯一配置模板、类型、默认值、环境读取 |
| `backend/main.py` | FastAPI 组装、MinIO lifespan；无 CORS 中间件 |
| `backend/app/api/report.py` | 上传/分析 NDJSON 传输、PDF API |
| `backend/app/api/chat.py` | 聊天 JSON 传输与图入口 |
| `backend/app/api/history.py` | 会话 CRUD、报告搜索/引用、PDF 上传 |
| `backend/app/api/assets.py` | 有界 raw body 读取、鉴权资源响应 |
| `backend/app/api/auth.py` / `app/auth.py` | 注册登录/profile、token |
| `backend/app/workflow/state.py` | 主报告状态定义 |
| `backend/app/workflow/graph.py` | 报告 DAG、ReportServices 节点、汇合/修复/取消 |
| `backend/app/workflow/orchestrator.py` | 图调用、媒体生命周期、对外结果映射 |
| `backend/app/workflow/upload_graph.py` | 上传节点、内存并发限制 |
| `backend/app/workflow/chat_graph.py` / `chat_policy.py` | 聊天条件边 / 保留的问答策略 |
| `backend/app/workflow/pdf_graph.py` | 按需 PDF 图 |
| `backend/app/workflow/role_policy.py` | 原角色路由启发式与归一化 |
| `backend/app/agents/` | scene/router/writer/title/PDF 提示词适配 |
| `backend/app/llm.py` / `llm_registry.py` | 模型工具子图 / 层级和采样参数 |
| `backend/app/tools/registry.py` | schema、可信上下文、工具执行器 |
| `backend/app/tools/video_tools.py` / `validation_tools.py` | 原视觉处理与报告校验函数 |
| `backend/app/prompts/` / `knowledge/` | 原报告/聊天 Prompt 与 quick guide |
| `backend/app/storage.py` | MinIO bytes I/O、所有权、补偿/引用清理 |
| `backend/app/persistence/{schema,database,repositories}.py` | 表定义 / 连接事务 / SQL 仓储 |
| `backend/app/db.py` | 兼容应用内部调用名称的仓储入口，不是旧 MySQL 实现 |
| `backend/alembic/` | 迁移环境、冻结版本 |
| `backend/app/pdf/report_pdf.py` | ReportLab 内存渲染 |
| `backend/app/yolov8m.pt` | 沿用的程序模型资源 |
| `backend/tests/` | 基线、工具协议、图、PG/MinIO、HTTP E2E |
| `frontend/src/App.jsx` | 应用状态、API 调用、流处理和上传 |
| `frontend/src/pages/ThreadContent.jsx` | 报告、图片及 PDF 菜单 |
| `frontend/src/components/PrivateImage.jsx` | bearer fetch、Blob 生命周期 |
| `frontend/src/pages/` / `layouts/` | 路由页、鉴权、个人资料与聊天布局 |
| `frontend/vite.config.js` | 不公开 env、容器内开发服务与 HMR；无 API 直连代理 |
| `docker-compose*.yml` / `gateway/` | 唯一入口、网络隔离、HTTP/S3/Console 代理及 TCP 扩展 |

主要 API（均有 `/api` 前缀）：`POST /uploadVideo`、`POST /processVideoStream`、`POST /processChat`、`GET /assets/{id}`、`POST /reports/{chat}/export-pdf`、`GET /reports/{chat}/pdf-latest`、`GET /reports/pdf/{report}/download`、`POST /reports/upload-pdf`；会话、登录和报告附件入口见对应 API 文件。

## 7. 验证范围和限制

最终结果见 [执行记录](REFACTOR_EXECUTION.zh-CN.md)。集成测试使用真实隔离 PostgreSQL 和 MinIO；外部 Qwen 响应固定替身，图测试核对分支/屏障/修复次数，工具测试核对真实 SDK 协议形状。另行跑过本地 YOLO 权重对内存数组的推理。没有调用付费模型进行实际报告质量评估。

浏览器验证了测试账户登录、历史报告、私有图片完整加载和预览、PDF 菜单；PDF 预览导航被浏览器安全策略拒绝，没有绕过。PDF 导出/下载/文件签名由 HTTP E2E 验证。

本机 macOS 的 PyAV 与 OpenCV wheel 各自附带 FFmpeg，运行时报告 Objective-C 重复类警告；本轮推理和测试通过，但不是已解决的平台兼容性问题。未执行完整容器镜像构建或从零安装全部视觉依赖；做了当前环境依赖一致性和关键模块导入/推理检查。

并发限制是单进程的，需按总进程数估算内存。上传未被使用的原始对象不会自动过期；报告进程重启会中断未完成工作；没有后台队列或清理调度器。旧数据库/卷/上传文件不在此次清理范围。
