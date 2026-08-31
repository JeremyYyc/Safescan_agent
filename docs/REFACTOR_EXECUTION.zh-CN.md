# 重构执行记录

集成分支：refactor/plan。阶段子分支均从当时的集成分支创建，验收后 --no-ff 合并，保留分支，不修改 main、不 push。

## P1 — unified-config

- 根 .env 为唯一实际配置；.env.example 为无秘密模板。删除四份 backend/frontend test/production env，历史由 Git 保留。
- Settings 为唯一环境读取入口，进程覆盖文件，秘密值不进入 repr；保留原模型分层、名称和采样参数。
- 前端空 API base 改为同源，开发代理与网关共用；根 env 不进入镜像，浏览器只公开 API base。
- 8 项单测通过；前端 build 通过；基础及两个 override Compose 校验通过。
- 隔离 MySQL：用户创建/验证、会话、消息、health API 与 OpenAI 客户端初始化通过。
- 原本地 httpx 0.28 导致旧 OpenAI 的 proxies 参数异常；固定为兼容的 0.25.2，不涉及业务逻辑。
- 原报告最后一次修复不再校验的行为已用基线测试记录，本阶段未修改。

## P2 — mysql-to-postgresql

- SQLAlchemy 连接池 + psycopg；领域仓储与 schema 分离，db.py 保持原调用入口。
- 十张表沿用原职责，bigint identity、UUID、JSONB、timestamptz、外键及索引、类型/互斥约束。嵌套仓储共享外层事务；报告和明细、消息和明细原子提交。
- Alembic 独立初始化；请求不再建表、改表、回填历史数据。初始迁移冻结 schema，不引用未来模型定义。
- 安全变更：新用户密码用随机盐 scrypt 替代 MD5；email 归一化唯一；不迁移旧数据。
- 同步仓储/模型处理进入 FastAPI 线程池，不阻塞请求事件循环。
- 13 项测试通过（含真实 PostgreSQL 注册、鉴权、CRUD、PDF/引用、约束与故障回滚）；Alembic check 无差异；Compose 配置通过。
- 删除三个旧 MySQL 历史升级脚本（只删除代码，未执行删库/删卷）；均可从 Git 历史恢复。

## P3 — local-storage-to-minio

- 私有 MinIO 业务对象 + PostgreSQL 文件元数据；只接受资源 ID，验证所有者，不允许任意路径/URL。
- 视频上传改为原始 body，返回 video_asset_id；抽帧使用 PyAV 内存解码，图片使用 bytes/数组，PDF 使用 BytesIO；删除 /uploads 静态挂载和本地文件回收实现。
- 图片使用带鉴权 API + 浏览器 Blob URL；VL 使用内联图像数据，不要求云模型访问私有 MinIO。
- 清理未被报告引用的处理中间对象；写对象后元数据失败会补偿删除。数据库与对象存储不具有共同事务，清理失败记录日志及元数据供重试。
- 有界上传/视频时长/分辨率与工作并发；网关关闭请求、响应临时文件缓冲。源码、权重、静态资源未迁移。
- 17 项测试通过；含真实 PG+MinIO、禁止 Path.open/上传 spooling 的视频抽帧与 PDF 渲染、跨用户访问拒绝及写入补偿。前端构建和 Alembic check 通过。
- 修复无效视频输入先占用处理锁的问题；PDF 空 checklist 现在按空列表处理。未调整报告评分、模型 Prompt 或修复轮数。
- 初始迁移要求新 Demo 空库，不删除旧上传文件、数据库或数据卷；P2 测试库仍保留。

## P4 — tool-calling

- 新增显式工具注册表：指南检索、报告读取、校验、抽帧、筛选、代表图选择、YOLO 标注；保留底层业务函数。
- Pydantic 严格 schema，拒绝额外参数；用户身份/会话/资源白名单/模型由服务器 ToolContext 注入，不接受模型传入身份。
- 标准 OpenAI-compatible tools → tool_calls → 执行 → role=tool/tool_call_id → 模型最终回复；支持多工具、重复调用 ID 校验、白名单及轮数/调用数/输出预算。
- 只读工具有超时；媒体写操作等待完成，并使用既有资源上限，避免以线程超时伪装成已取消写入。
- SDK 固定 OpenAI 2.54.0 + HTTPX 0.28.1；没有更换 Qwen 模型、添加旧 AutoGen 工具适配或提前搭建报告图。
- 26 项测试通过，包括协议请求/回传、多调用关联、非法参数/身份、未知工具、预算及前三阶段回归。模型响应使用确定性替身，不宣称真实模型效果已验证。

## P5 — autogen-to-langgraph

- 上传、报告、聊天、PDF、模型/工具循环全部使用 LangGraph。主报告图由 typed state、角色并行汇合、条件退出和有限修复环组成，不是将旧 orchestrator 塞进单一节点。
- 聊天明确分为 guide/report/multi-report/smalltalk/safety/refusal 条件边；PDF 保留按需触发；上传和分析继续分为两次 HTTP 请求，由稳定资源 ID 衔接，不增加自动开始分析或断点恢复功能。
- `run_id` 标识每次报告执行；状态不持有密钥、连接、模型对象或图片字节；trace reducer 合并并行节点记录。
- 移除 AutoGen base/proxy/client、旧 agent team/react loop 和依赖声明；复用 P4 的标准工具协议，保留原模型层级/参数、提示词、筛选/评分/修复政策。
- 必要错误语义修复：原同步/异步调用边界失败；报告保存失败由 complete 改为 error/end，并用故障注入验证未保存报告。校验耗尽仍保存的旧政策没有改变。
- 端到端联调修复视频 body 仍引用旧 FormData 的遗漏；整理 React effect 和未使用变量，前端 lint 无错误/警告。根 env 精确公开白名单、Compose 配置透传和上传并发限制作为图接入的集成修正。
- 统一配置只剩根 `.env` 与无秘密 `.env.example`；当前 44 个配置项都有模板说明，26 个未启用历史本地值改为注释留存，真实值未提交。环境变量技能仅用于密钥/公开变量边界检查，没有采用其多环境副本方案。
- 新增当前架构与路径索引，原分析/路径文件明确标为重构前基线。

### 最终验收

- **44 passed**：报告共同基线、配置覆盖、PG 事务/约束、MinIO 所有权/补偿/无磁盘业务 I/O、工具协议、图条件边/汇合/修复、上传限额、HTTP 视频到报告到 PDF、聊天与保存失败路径。
- PostgreSQL/MinIO 使用真实隔离服务，Qwen/端到端 YOLO 输出使用固定替身；另行真实加载项目 YOLOv8m 权重，对内存数组推理通过。未调用付费 Qwen，不能宣称真实报告质量或云模型工具兼容性已验证。
- `npm run lint`、`npm run build` 通过（48 modules）；前端仅允许精确 `VITE_API_BASE`，同前缀秘密变量不会公开。
- Alembic check：No new upgrade operations detected；基础/test/prod 三种 Compose config 校验通过。
- pip check：No broken requirements found；关键模型/数据库/存储模块可导入。未从零安装全部视觉依赖或完成容器镜像构建。
- `git diff main@79bf95f -- backend/app/prompts` 无变化；活跃源码无 AutoGen/MySQL 连接、本地上传写入或 uploads 静态挂载。
- 浏览器实际验证测试账户登录、历史报告、所有图片加载和图片预览、PDF 菜单。PDF 预览导航被浏览器安全策略阻止，没有绕过；其生成和下载由真实 HTTP 集成测试覆盖。
- macOS PyAV/OpenCV 附带 FFmpeg 有重复 Objective-C 类警告，推理通过，但该平台兼容性风险未消除。

### Git 记录

| 阶段 | 保留的子分支 | 阶段提交 | 集成 merge |
|---|---|---|---|
| P1 | refactor/unified-config | 3cf046a | 2013c7e |
| P2 | refactor/mysql-to-postgresql | 6e7e3e8 | aa5a356 |
| P3 | refactor/local-storage-to-minio | 5813aa0 | 5dc31e6 |
| P4 | refactor/tool-calling | d0c4439 | bc46239 |
| P5 | refactor/autogen-to-langgraph | 见该分支 tip | 见 refactor/plan 的最后一次 merge |

各阶段从当时的 refactor/plan 创建，测试后 --no-ff 合并；保留所有子分支，main 不变，不 push。不删除旧上传目录、数据库或数据卷。测试创建的 safescan-refactor-* 容器/数据保留供复验。

### 保留边界

最后一次修复不再校验、进程中断不恢复未完成图、未引用上传对象无自动过期、跨 MinIO/PG 故障需人工对账，均明确记录在当前架构文档。源码、权重与静态资源属于程序资源，没有迁入 MinIO。

## 后续 — nginx-gateway

- 基于 refactor/plan@a940dcb 新建 refactor/nginx-gateway；只修改网关、连接配置及验证，不修改报告图或提示词。
- Nginx 成为唯一发布端口的服务：应用 8080、S3 9000、Console 9001（默认宿主机 loopback）。前端固定相对 /api；移除 CORS_ORIGINS/CORS_ORIGIN_REGEX/VITE_API_BASE 和 CORS 中间件。
- 后端 MinIO SDK 指向 gateway:9000；只有 gateway/MinIO 加入 storage 内网。PostgreSQL 仍保持后端内部连接，无主机映射。所有 Compose 变体都保留网关，开发 Vite 也不发布绕行端口。
- 保留 S3 签名 Host/URI/query、WebSocket Upgrade、NDJSON 实时传输与无磁盘缓冲；新增动态 DNS 上游、代理后 MinIO readiness，消除启动循环。
- Redis TCP stream 和 worker HTTP 扩展示例默认不启用；两份示例启用后的 nginx -t 通过，没有安装 Redis/worker。
- **49 passed**：45 项本地/PG/MinIO 回归 + 4 项真实 Nginx HTTP、流式首块、S3 多段/特殊字符/预签名 Range、控制台测试。存储测试通过 Nginx S3 入口运行，Qwen 使用固定响应。
- 网关和前端 Docker 镜像构建成功；前端 lint/build 通过；三个 Compose 变体确认只有 gateway 发布端口，后台不能直连 storage 网络，无依赖循环。Nginx 生效配置检查和代理后的 MinIO readiness 通过；测试日志未出现 X-Amz 签名查询参数。
- 前端 npm ci 报告既有 15 项依赖漏洞（1 low / 5 moderate / 9 high），未修改 lockfile 或自动升级。没有在日常数据卷上启动全套 Compose；浏览器 HMR 尚未交互验证。旧 macOS FFmpeg 警告仍保留。
- 后端架构技能用于检查代理/鉴权/组件职责，环境变量技能用于秘密隔离；仍只维护根 env，不引入 Vercel 或多环境 env。
- 具体配置、协议边界、未来扩展和复验入口见 [Nginx 网关](NGINX_GATEWAY.zh-CN.md)。
