# Safe Scan Agent 分阶段重构计划

日期：2026-08-31。代码基线：`main@79bf95f`。

状态：仅规划；尚未开始业务代码重构。本文替代此前分析报告中的生产化演进建议，作为本轮重构的范围依据。

## 1. 约束与交付原则

1. 项目是 Demo，没有需要保留的生产数据。允许直接替换实现、建立新库，不设计灰度、双写、MySQL 数据搬迁、旧数据库兼容或生产上线流程。
2. Git 保存历史；不为回退长期保留两套 Agent、数据库或存储实现。
3. 保持原报告生成的业务步骤、模型分工、Prompt 语义、筛选/评分规则和结构化输出。架构迁移不夹带报告质量策略调整。
4. 本地能力通过真实 tool calling 接入 LLM；不能仅给 Python 函数加一个装饰器或在日志里写 tool_call 就宣称完成。
5. 每个分支只处理一个目标；完成本阶段验收后才开始下一阶段。每次交付报告提交 SHA、测试结果、已知限制。
6. 不引入用户未要求的 Celery、Redis、向量 RAG、OCR、LangSmith 云服务、Kubernetes 或大型前端改造。
7. 仅修改本地运行和集成测试所需的 Compose 配置，不开展生产部署设计。
8. 根目录现有 `.env` 有用户本地内容：不覆盖密钥、不提交真实值。统一配置时逐项合并，保留有效配置。
9. “不迁移旧数据”不等于执行任意删库/删卷；本轮计划不会删除任何数据库、MinIO 对象或上传目录。后续若确需清理，先定位具体 Demo 资源，不能使用宽泛清理命令。

## 2. Git 分支与阶段顺序

采用简单串行集成：每个功能分支从上一阶段已经验收并合入后的 main 创建，不一次性创建全部分支，不建立长期混合重构总分支。

| 阶段 | 分支 | 唯一主题 | 不允许夹带 |
| --- | --- | --- | --- |
| P0 | `refactor/plan` | 分析文档、范围、验收标准 | 业务改动、配置值变更 |
| P1 | `refactor/autogen-to-langgraph` | Agent/Workflow 架构迁移及等价性测试 | PostgreSQL、MinIO、工具自治、Prompt 重写 |
| P2 | `refactor/tool-calling` | 工具 schema、注册、LLM 调用闭环、必要接线 | 视觉算法/报告规则调整、数据库引擎迁移 |
| P3 | `refactor/mysql-to-postgresql` | 数据访问层、表结构、事务、数据库替换 | MinIO 接入、模型/图逻辑变化 |
| P4 | `refactor/local-storage-to-minio` | 私有对象存储、无应用侧文件落盘、资源 API | 报告内容策略、评分与筛选算法优化 |
| P5 | `refactor/unified-config` | 单套 env、Settings、配置消费与文档收口 | 新业务功能、额外基础设施 |

顺序：P0 → P1 → P2 → P3 → P4 → P5。tool calling 单独插在架构迁移后，以便清楚区分“换运行框架”和“改变调用协议”。

配置统一安排在最后是为了保持当前用户目标顺序以及分支责任清晰。P1–P4 只补各自运行必需的配置，不能再增加新的环境文件体系；P5 一次收敛所有已确定的键。根目录现有 PostgreSQL/MinIO 配置可作为配置资料参考，不直接当作已验证运行配置。

### 每阶段 Git 操作约定

- 开工前查看 `git status`，只提交本阶段文件；禁止 `git add .` 混入本地 env 或其他工作。
- 分支内使用小型、可解释的提交，例如 `test(workflow): capture report invariants`、`refactor(workflow): replace autogen with state graph`。
- 提交前检查 staged diff、秘密文件排除情况与测试结果。
- 验收后使用普通 merge commit 合入 main，保留分支主题，不使用强推或 reset 覆盖历史。
- 下一阶段从新的 main 创建，未验收的阶段不得合入。
- 本轮只创建/提交计划分支，不合并 main、不 push、不创建后续实现分支。

已存在的 `codex/refactor-langgraph-platform`、`codex/docker-env-migration` 等历史分支保持不动；它们可能混合其他目标，不能直接 merge/cherry-pick 替代本次分阶段实现。当前源码基线由提交 `79bf95f` 保留。

## 3. 首先固定“不能改变”的业务逻辑

P1 第一个代码提交先添加 characterization tests（现有行为刻画测试），而不是立即改写实现。

| 业务项 | 保持内容 |
| --- | --- |
| 视频输入 | 用户提交视频和现有六类人群属性；保留用户/会话归属检查 |
| 抽帧与筛选 | 1 fps 目标抽样、pHash/模糊/暗帧/人脸过滤顺序与现有阈值 |
| 代表图选择 | 现有分段、候选采样、房间规则和加权排序，不趁迁移优化算法 |
| YOLO | 使用当前权重与检测参数，不训练/替换模型 |
| 场景分析 | VL 视觉理解、解析、房间分组、YOLO fallback |
| 角色计划 | Router + 原启发式兜底；Hazard 和 Writer 必须保留 |
| 第一阶段依赖 | Hazard 与可选 Comfort 同阶段，可并行 |
| 第二阶段依赖 | 第一阶段完成后运行可选 Compliance/Scoring，并等待汇合 |
| 后续依赖 | Recommendation 依赖 Scoring；Writer 等待所有选中角色的结果 |
| 报告输出 | 保持 regions、scores、meta、recommendations 等字段及语义 |
| 校验修复 | 保留现有 Validator 规则与最多 3 轮的修复政策，不增减业务校验规则 |
| 报告完成后 | 证据图片关联、标题、持久化、历史展示仍可用 |
| PDF | 保持用户请求时导出，不擅自改为每个视频强制生成 PDF |
| 聊天 | 保留意图类别、指南检索、单/多报告解释及闲聊限制 |
| 模型配置 | 保留 Qwen 的 L1/L2/L3/VL 分层和现有 generation 参数，不悄悄换模型 |

使用固定模型响应和合成/无敏感视频样本对比结构化结果、节点依赖、工具结果及关键 trace；过滤 UUID、时间戳等非确定字段。真实 LLM 文本不保证逐字一致，不以自然语言逐字相等作为唯一验收标准。

历史缺陷不应伪装成架构优化：P1 必須修复由 AutoGen 同步/异步边界导致的调用失败，并单独记录。评分字段变更、筛选参数调整、修复轮数边界改动、“校验失败仍返回 complete”等独立业务/错误语义变化，先记入问题清单，不顺手混入纯架构分支。必要修复若确实影响既有响应，须在提交中明确旧/新行为和测试依据。

## 4. P1：AutoGen → LangGraph

### 4.1 目标

真正用节点、边、条件边和统一状态表达完整过程，不能只把旧 orchestrator 整体塞进一个 LangGraph 节点。

上传字节的 HTTP 接收仍是 API 传输职责；上传校验/资源接收、分析、报告组装和保存成为工作流可追踪阶段。保留当前上传/分析两步交互，通过服务端 run_id/状态衔接；不要求前端一次提交后自动开始分析。若需要跨这两个请求暂停/恢复，Demo 使用受控的内存 checkpoint，不引入 Redis 或生产任务平台；进程重启不保证未完成任务恢复，界面应明确需重试。

### 4.2 主图设计

```text
接收上传 / ingest_video
  → uploaded（等待用户启动分析）
  → validate_input
  → extract_frames
  → filter_frames
  → select_representatives
  → detect_objects
  → understand_scene
  → plan_specialists
  → [hazard || comfort 或显式 skip]
  → stage1_join
  → [compliance 或 skip || scoring 或 skip]
  → stage2_join
  → recommendations 或 skip
  → write_report
  → validate_report
      ├─ 需修复且轮数未耗尽 → repair_report → validate_report
      └─ 原有终止条件       → finalize_report
  → attach_evidence
  → generate_title
  → persist_report
  → END
```

空帧、空证据、模型错误通过显式终止路径处理。阶段 join 等待所有激活分支，不可因可选节点被跳过而死等，也不能使 Writer 提前/重复执行。修复循环如何计数按 P1 行为基线精确定义，不能仅照示意图改变最后一轮的执行语义。

PDF 独立子图：load_report → normalize → pdf_repair → render_pdf → persist_pdf → END；保留按需触发。其修复 LLM 也必须去掉 AutoGen。

聊天原来并非全部使用 AutoGen，但目标是统一运行架构：迁出 API 中的编排，建立 classify → guide/report/multi-report/safety/refusal 条件子图，复用既有分类 Prompt 和业务政策，不新增功能。

StateGraph 支持 typed state、节点增量更新和条件路由；并行共享字段必须定义合并规则。这些机制适合这里的显式分阶段工作流。[LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)

### 4.3 状态与依赖边界

状态至少表达：run_id、chat_id、输入资源引用、用户属性、frame refs、筛选统计、代表图、YOLO 摘要、region_evidence、plan、hazards、comfort、compliance、scoring、recommendations、draft/final_report、validation、repair_count、trace 和终止原因。

- 可序列化的运行数据放 state；API key、数据库 session、模型客户端、上传流、YOLO 对象放 runtime dependencies/context。
- 用户身份由服务端鉴权注入，不能由模型或表单自行覆盖。
- 并行角色写各自结果字段；共享 trace 以稳定标识合并，不能多个节点原地修改一个字典。
- P1 允许资源引用仍指向现有本地存储；不要提前做 MinIO。先用薄资源边界隔离具体路径，让 P4 只替换存储实现。
- 内部图事件映射回当前 NDJSON trace/complete/error/end，避免因换框架顺手重写前端协议。
- 外部 I/O 使用一致的 async 调用入口；CPU 图像处理离开事件循环；不嵌套 asyncio.run。

### 4.4 计划中的目录职责

以下是拟新增/重组路径，不表示已经存在：

```text
backend/app/workflow/
  state.py                    typed workflow state
  graph.py                    主图及编译入口
  nodes/                      视频/场景/角色/校验/保存节点
  chat_graph.py               聊天条件子图
  pdf_graph.py                按需 PDF 子图
  events.py                   图事件 → 现有 API 事件
backend/app/llm/
  client.py                   Qwen 客户端接口与兼容协议适配
  schemas.py                  结构化模型输出约束
backend/app/services/
  report_service.py           API 与图的衔接，不保存第二套业务流程
backend/tests/workflow/       图拓扑、状态、分支和旧/新结果对照
```

移除 AutoGen adapter/base/proxy 的活跃依赖和 pyautogen；Prompt 文件优先原样复用。保留 OpenCV/YOLO、MySQL、现有文件存储。准确依赖版本在本阶段的兼容性验证中选定并锁定，不继承目前 OpenAI/httpx 的不兼容组合。

### 4.5 子任务与验收

1. 行为基线和模型 fake provider。
2. typed state、LLM client、图节点与边。
3. API 事件桥接、上传/分析关联、PDF 和聊天子图。
4. 删除 AutoGen 残留依赖，检查 fresh install。
5. 验证全角色/可选角色跳过、空证据、模型解析失败、修复 0/1/多轮、耗尽、保存失败、并行 join 和状态不串任务。
6. 无 AutoGen 活跃 import；视频到报告主路径通过 mock E2E；原前端能消费事件和展示报告。

完成 P1 后停止，只报告结果，不自动进入 P2。

## 5. P2：真实 tool calling

### 5.1 工具范围

业务实现与工具包装分离；为现有本地能力建立显式注册表、类型 schema、简洁描述、输出结构、超时与错误模型。

| 类别 | 拟提供的工具 | 调用限制 |
| --- | --- | --- |
| 视频 | extract_frames、filter_frames、select_representatives、detect_objects | 仅当前任务资源；原参数由运行上下文控制 |
| 报告 | validate_report、render_report_pdf | 不改变规则；render 仅显式导出流程可用 |
| 知识 | search_guide | 保持当前检索策略 |
| 已有数据 | get_report_context / get_active_report_context | 只读、当前用户授权资源 |

鉴权、数据库任意 SQL、文件删除、凭据读取、持久化提交不是交给 LLM 的自由工具。模型不能提供任意磁盘路径、任意 URL、user_id、数据库连接串或 MinIO endpoint。

### 5.2 调用协议

形成真实闭环：模型收到 tools schema → 返回 tool_calls（name、arguments、id）→ 注册表/ToolNode 执行 → ToolMessage 匹配 tool_call_id → 回到模型或图内下一阶段。参数和返回结构都验证；权限和依赖从服务端 runtime 注入，不进入模型可填写参数。相关机制见 [LangChain Tools](https://docs.langchain.com/oss/python/langchain/tools)。

主图仍强制业务阶段顺序；工具调用子循环嵌入对应节点，只暴露本阶段许可的工具。固定参数由服务端控制，LLM 不能借 tool calling 改 1 fps、评分规则或跳过必需筛选。

所选 Qwen 模型与思考模式是否支持所需 tool_choice 必须测试；不能仅相信 `required` 就假设一定会返回 tool_calls。未调用必需工具、未知工具、非法参数或超预算时应显式失败/重试，不允许伪造工具结果或静默跳过步骤。[Qwen Function Calling](https://help.aliyun.com/en/model-studio/qwen-function-calling)

工具返回摘要和 asset refs；不把整个视频、所有图片二进制或完整任务状态灌入模型上下文。工具执行次数与报告修复轮数是两个独立预算。

### 5.3 验收

- 每个工具有明确 schema、服务端权限注入和测试。
- 至少覆盖视频工具、报告校验和知识检索的完整 tool_call → 执行 → ToolMessage 闭环；PDF 工具在导出子图验证。
- 主业务工具实际经模型调用路径运行，而非仅注册未使用。
- 记录 tool_call_id、工具名、耗时、输出摘要，隐藏凭据与敏感数据。
- 覆盖未知工具、非法参数、重复调用、副作用幂等、超时、无 tool_calls、非法资源和循环预算。
- 与 P1 固定输入对照，报告语义和必需阶段不变。
- 用 mock 验证协议不等于云端兼容性已验证；真实模型 smoke test 的结果单列，无可用凭据时明确未验证。

## 6. P3：MySQL → PostgreSQL

### 6.1 数据层选择

计划采用 PostgreSQL + SQLAlchemy 2.x + psycopg 3 + Alembic。SQLAlchemy 的 PostgreSQL 方言支持 psycopg 3；此处使用 session/连接池管理和显式事务，替代当前散落的连接与 SQL。[SQLAlchemy PostgreSQL/psycopg](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg)

新建 Demo schema，不导入旧 MySQL 数据、不维护双数据库读写。Alembic 用于新 schema 的可重复创建和后续开发变更，不是生产灰度流程。业务请求不再执行 CREATE/ALTER/历史回填。

将现有大 db.py 拆为 engine/session、models、repositories；graph 与 API 使用仓储接口，不自行拼接存储 SQL。同步/异步 session 选择在 P3 实施前与 P1 I/O 边界核对；不允许同步数据库操作无包装地阻塞 async API。

### 6.2 沿用的领域模型

保留 users、chats、messages、chat_details、reports、report_analysis、report_pdf、files、report_assets、chat_report_refs 十张表的职责和报告分型思路。

| 设计项 | 改造方向 |
| --- | --- |
| 主键 | 内部 bigint identity；公开 UUID 使用 PostgreSQL uuid 类型，外部公开 ID 编码集中处理 |
| 用户 | email 归一化后唯一；password_hash 宽度满足标准密码哈希。若替换 MD5，作为 P3 用户仓储改造中的独立提交和明确行为变更 |
| 时间/布尔 | timestamptz、boolean；统一时区处理 |
| JSON | 分析报告、区域、meta 使用 JSONB，应用层仍校验业务结构 |
| 外键 | 统一关联列类型，定义 FK；高频引用列有索引 |
| 唯一约束 | chat/report UUID、chat-report 引用、report asset 组合等 |
| 数据一致性 | report_kind/pdf_kind/status 等 CHECK；chat_details 消息或报告引用的互斥约束 |
| 删除规则 | 附属记录可 cascade，跨会话报告引用和来源保留规则先写测试再选 cascade/restrict/set null，不全表一律级联 |
| 事务 | 报告主记录+类型子表+资源关系在一个事务内；消息与明细同理 |
| 索引 | 依据 user_id/created_at、chat_id/created_at、report refs 和文件关联查询建立，不给每个 JSON 字段盲目加 GIN |

数据库 FK/UNIQUE/CHECK 用于约束数据关系，不替代 API/工具的用户授权检查。[PostgreSQL Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html)

files 在 P3 仍保存可工作的本地资源元数据，不提前接入 MinIO；P4 再把定位方式改为 bucket/object_key。允许后续开发迁移，不需要一次预造全部未来字段。

### 6.3 验收

- 干净 PostgreSQL 实例可创建完整 schema，初始化不依赖历史库。
- 注册/登录/资料、会话 CRUD、消息、报告保存/查询、引用/删除、PDF 记录回归通过。
- 唯一约束、外键与跨表事务回滚有集成测试；请求路径无 DDL。
- 活跃实现不再使用 PyMySQL/MySQL 方言；旧 MySQL 历史升级脚本退出当前运行入口。
- 仅调整本地 Compose 的数据库服务，不设计生产搬迁。

## 7. P4：本地业务文件 → 私有 MinIO

### 7.1 存储范围待确认

已向用户确认“所有文件”是否指视频、抽帧图片、报告/PDF 等业务文件，是否包含模型权重和前端静态资源。此问题不阻塞 P1，但 P4 实施前必须明确。

当前严格工作假设：**所有业务文件的持久副本只在 MinIO，应用进程也不使用临时磁盘文件。** 不默认将“不能保留本地文件”放宽为“先落盘、上传后再删”。若用户允许临时文件，再明确调整这一条。

MinIO 本身需要自己的数据卷持久化对象，这与“业务应用不将文件落到 uploads/tmp”是不同边界。源码、env、依赖与模型权重的安装介质不擅自迁移，等待范围确认。

结构化报告 JSON 仍是 PostgreSQL 的业务记录；若产生 JSON 导出文件，该文件进入 MinIO，不把“文件都进 MinIO”误解成数据库结构化字段也必须删除。

### 7.2 实现边界

- ObjectStorage 接口提供 put/get/stat/remove/受控读取，不暴露本地绝对路径。
- 原视频、帧、标注图、上传 PDF、导出 PDF 使用私有 bucket；对象 key 由服务端按 user/run/asset 生成。
- files 改为 bucket、object_key、mime_type、size、checksum、所有者及业务关联；不把短时 URL 存作永久定位，也不把 ETag 无条件当作内容 MD5。
- 前端/API 只传 asset_id、run_id 或受控资源 URL，不再提交服务器 video_path。
- 移除公共 `/uploads` 挂载、路径字符串截取与本地文件回收代码。
- 私有读取优先通过后端鉴权代理；如使用预签名 URL，生成前验证资源归属并限制时效。不会将 MinIO 开成公共 bucket。
- 云端 VL 输入通过后端读取对象字节后组成图像输入，不把本机私网 MinIO 地址直接交给云模型访问。

MinIO Python SDK 提供基于可读流的 put_object/get_object，可用于无持久落盘的对象读写；具体版本接口在实施时固定并验证。[MinIO SDK API](https://github.com/minio/minio-py/blob/master/docs/API.md)

### 7.3 严格不落盘需要额外覆盖的点

1. HTTP multipart 上传不能依赖可能自动 spool 到磁盘的默认路径；核对上传解析器和网关缓冲，采用有界流/内存分片，必要时在本分支调整上传协议。
2. 当前 OpenCV VideoCapture 依赖文件路径，需引入可从对象流/内存解码的适配（候选 PyAV 或受控 FFmpeg 管道）。只替换 I/O，不改变抽帧、过滤、评分与 YOLO 参数；用固定样本验证帧索引和内容偏差。
3. 图片处理使用数组/bytes，编码后直接上传，不再 imwrite 到 run 目录；保留算法实际选择的帧，不擅自扩大数据保存范围。
4. ReportLab 输出到 BytesIO/流后存对象，不生成本地 PDF。
5. state 只保留 asset refs，不装入全视频；设置上传字节/视频时长/分辨率/内存上限及流式背压，避免“不落盘”变成无限内存。
6. 数据库和 MinIO 不具备共同事务：采用明确写入顺序、失败清理及可测试补偿，不能声称 PG 事务会自动回滚 MinIO 对象。

### 7.4 验收

- 上传视频 → 分析 → 图片展示 → 历史重开 → PDF 导出/上传/下载全部使用 MinIO。
- 非所有者访问失败；对象 key 不由模型或客户端任意指定。
- 完成、失败、取消三类路径都不产生业务本地文件；测试覆盖应用与上传链路临时落盘，而不只检查 uploads 目录。
- 重启应用后，已经完成的报告仍可通过 PG+MinIO 重建，不能依赖进程内文件缓存。
- 断流、对象不存在、写入失败、数据库失败及删除引用等情况有测试。
- 本地服务加入 MinIO，仅用于 Demo 自托管；不扩展到集群、云部署或生产迁移。

## 8. P5：一套配置，统一收口

最终仅保留根目录 `.env`（实际值、Git 忽略）和 `.env.example`（相同键的无秘密模板、Git 跟踪）。这是“一套配置的实际文件+示例”，不是两套 test/prod 配置。不会保留 backend/frontend/app 下的多份 .env.test/.env.production。

拟按以下分区注释：

1. 应用：模式、时区、日志等级。
2. PostgreSQL：连接信息/URL、连接池参数。
3. MinIO：endpoint、凭据、TLS、bucket、读取有效期。
4. Qwen：API key、base URL、L1/L2/L3/VL、请求超时。
5. Workflow：并发、修复轮数、tool-call 预算；默认值保持既有业务政策。
6. 上传/资源：字节、时长、分辨率和内存限制。
7. 鉴权：token 签名、期限、公开 ID 密钥。
8. 浏览器与本地入口：只含可公开的 VITE_*、CORS、必要端口。

后端使用集中 Settings、类型验证、显式错误信息；业务模块不再多处 load_dotenv/os.getenv。前端 Vite 从根配置读取，只有 allowlist 中的公开配置可进入浏览器包；后端/MinIO/数据库密钥不得加 VITE_ 前缀。测试通过依赖注入/受控覆盖构造配置，不再新增物理 env 文件。

配置优先级：显式测试/调用覆盖（仅受控代码）→ 已注入进程环境 → 根 `.env` → 非秘密默认值；`.env.example` 不在运行时加载。缺少必要凭据时报配置错误，不生成伪默认生产密钥。

Compose 使用同一个根 env 的明确字段，避免把所有密钥无差别注入每个服务。合并重复数据库密码来源、模型变量命名和 base URL 设置；分区注释解释使用方、单位、必要性及本地容器/宿主机区别。

验收：

- 扫描仓库，除根配置对外无第二套活跃 env；example 与 Settings 键一致。
- 现有真实值被安全保留，Git 和前端 bundle 不含密钥。
- README 的初始化、启动、测试命令只要求维护这一套配置。
- 清洁环境可安装固定依赖并启动本地 Demo；不因默认工作目录不同加载错 env。

## 9. 每阶段交付检查表

- 范围检查：本分支没有下一阶段实现或无关重构。
- 行为检查：冻结的报告业务不变量仍满足；任何例外有说明。
- 测试检查：新增测试实际运行，明确 mock 与真实集成的区别。
- 依赖检查：变更依赖可重复安装，无残留 AutoGen/MySQL/本地文件活跃路径（按阶段要求）。
- 安全检查：工具权限不由 LLM 决定，真实 env 不进 Git，资源属于当前用户。
- Git 检查：仅提交精确文件，记录 SHA；未请求时不 push。
- 阶段总结：完成项、测试、已知限制、下一阶段入口；本轮到阶段边界停止。

本次基于 backend-patterns 的分层/事务思路和 PostgreSQL 设计技能制定数据层边界，不引入 Supabase 服务；LangGraph/Tool calling 的 API 能力已核对官方文档，具体版本和模型兼容性仍须在对应实现阶段验证。

## 10. 本轮完成范围与下一步

本轮：检查当前基线、记录重构约束、创建计划分支并提交规划资料。没有安装依赖、调用付费模型、迁移数据库、接入 MinIO或修改业务代码。

下一轮仅执行 P1：从行为刻画测试开始，然后实现 LangGraph 状态和图。P2–P5 均保持未开始；MinIO 文件范围与临时文件规则待用户确认后再定稿。
