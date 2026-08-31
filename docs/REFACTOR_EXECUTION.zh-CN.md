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
