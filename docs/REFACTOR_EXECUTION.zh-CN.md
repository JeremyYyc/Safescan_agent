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

## 启动修正 — postgresql17-volume

- 实际启动发现历史 `safescan_agent_postgres_data` 是 PostgreSQL 16 物理目录，不能由当前 17 镜像读取。用户确认不迁移旧数据，改用独立 `postgres17_data` 新卷；旧卷不再挂载，没有执行全局数据卷清理。
- 在 `refactor/postgresql17-volume` 修正 Compose，三个 Compose 组合均通过配置检查，验收后合并并保留分支。
- 完整后端镜像首次构建成功，五个服务已实际启动。PostgreSQL 17.10 健康，Alembic 版本 `20260831_0002`，新库 users=0。
- Nginx 后的前端、MinIO Console、S3 ready 均返回 200；`/health` 返回 ok，未登录 `/api/chats` 返回预期 401。后端经 `gateway:9000` 成功读取三个私有 bucket。
- 本次仅启动和连通性验证，未调用付费模型。现有宽范围视觉依赖安装了 CUDA 依赖链，首次构建耗时较长；未在启动修正中顺带调整依赖策略。

## 运行修正 — opencv-runtime-fix

- 从 `refactor/plan@127bd2a` 创建 `refactor/opencv-runtime-fix`。实际视频在 `filter_video_frames` 失败：Docker 安装的 OpenCV 包 5.0.0.93 没有 `cv2.CascadeClassifier`，本地已验证的 4.13.0.92 存在该接口。原声明只有下限，造成新镜像依赖漂移。
- 将 OpenCV 精确锁定为 4.13.0.92，Docker 构建时实际加载 Haar 模型并运行检测；不关闭人脸筛选，不修改原有阈值、报告图、提示词或报告生成政策。
- 工具失败时记录服务器端工具名称、异常类型及调用栈位置；不记录参数、局部变量或异常消息，避免暴露密钥和业务内容。模型/客户端仍只收到 `tool_failed`。
- 新增不依赖 pytest 的镜像内回归测试：真实 Haar 加载/检测、清晰图保留、重复图/模糊图/暗图剔除。仅替换存储边界，全部使用内存合成图片，不读取或删除用户资产。
- 旧镜像运行上述 4 项测试全部因缺失 CascadeClassifier 失败；本地相关回归 **38 passed**，本地 `pip check` 通过。新后端镜像构建及 Haar 检查通过，独立容器内上述 **4 项真实筛选测试全部通过**；项目 YOLOv8m 权重对内存数组的 CPU 推理通过。
- 容器内 `pip check` 返回 `nvidia-cusparselt-cu13 0.8.1 is not supported on this platform`；旧运行镜像也返回同一提示，属于现有 CUDA 依赖链的平台兼容性问题，并非此次 OpenCV 锁版引入。本次不顺带改变 PyTorch/CUDA 安装策略；不宣称容器依赖检查完全通过，也未调用付费 Qwen 验证完整报告质量。

复验入口（无需给运行镜像安装 pytest，不调用云模型）：

```sh
docker compose run --rm --no-deps backend python -m unittest discover -s tests -p test_video_runtime.py -v
docker compose exec -T backend python -m pip check
```

## 运行修正 — keyframe-filter-fix

- 基于 `refactor/plan@1a567e6` 创建 `refactor/keyframe-filter-fix`。实际请求的网关日志显示上传和 25 次派生帧写入成功，随后 25 帧全部被筛选删除；没有新的 OpenCV 接口异常。
- 只读读取对应的 3840×2160 视频，在内存中复现原筛选得到：抽取 25、保留 0；similar=4、blurry=20、dark=0、sensitive=1。所有写入/删除替换为内存操作，原视频及业务数据未修改。
- 根因：在原始 4K 像素上直接使用固定 Laplacian 方差门槛，对分辨率敏感；同时，已经被质量/人脸规则剔除的帧仍被设为后续去重基准。修改为最长边 960 的等比例、只缩小清晰度测量（不缩放证据资产），筛选和代表图排序使用同一指标；去重仅与上一张已保留帧比较。原阈值 25/50/50 和全分辨率人脸检测保持不变，无保底放行机制。
- 相同视频在 Linux 容器只读挂载修复代码后，实际抽帧/筛选/YOLO 代表图选择结果：**25 → 4 → 3**；新筛选统计 similar=0、blurry=2、dark=0、sensitive=19。人脸规则命中不等于已人工确认真实人脸，未更换检测器或绕过过滤。
- 日志及流式 trace 增加各阶段输入/输出数量和剔除分类；返回 `frameStats`。无帧/无证据提前退出时发送 error/end，不再发送伪成功 complete；沿用前端已有错误展示，不生成空报告。应用日志接入已有 APP_LOG_LEVEL。
- 本地相关回归 **44 passed**；Linux 容器 **8 项视频运行测试 + 2 项诊断/流式错误测试通过**，包括 4K 测量、拒绝帧不影响后续合格帧、全人脸仍全拒绝、全空不调用模型及错误流不标成功。未调用付费 Qwen 或更改报告生成提示词/评分逻辑。
- 本次依赖声明和标准 Dockerfile 未修改。标准重建未命中安装缓存且下载明显变慢，取消该次构建；复用已验证镜像 `sha256:954839dcb6224265504a34409b63960c83606a6bf6da8f68a7c19c9a3dfc662d`（本地保留标签 `safescan_agent-backend:opencv-verified-164a585`），仅 COPY 当前 backend 代码并在镜像内执行上述 10 项测试，全部通过。新镜像 `sha256:5a217934795a81aa3caced42b4b62840b5ee323cb875790823d5f2e9bc9bf38b` 已替换运行后端；其他服务/数据卷不变。网络正常时仍可用标准 `docker compose build backend` 从标准 Dockerfile 构建。
- 重启后 Nginx `/health` 返回 200，后端启动完成；实际运行后端对同一原视频再次只读复验，仍为 **25 → 4 → 3**。全部五个服务运行，未删除原视频、数据库或 MinIO 数据。
