# SafeScan AI Property Inspection Platform PRD

**版本**：v1.0 Frozen Baseline
**日期**：2026-08-27
**状态**：已冻结（P00/P0 开发基线）
**关联文档**：[技术扩展与升级方案](./technical-upgrade-plan.md)

## 1. 摘要

SafeScan 当前是一个基于视频的家庭安全分析原型：用户上传视频，系统通过 YOLO、视觉模型和多 Agent 流程生成安全报告。本 PRD 定义其下一阶段产品升级：将 SafeScan 演进为能够理解视觉证据、引用可信知识、追踪房屋历史并生成可解释检查报告的 AI Property Inspection Platform。

首个可交付版本先完成 P00 CI/CD 基线，再完成 PostgreSQL 迁移，再重构报告工作流并扩展 Safety Knowledge RAG。MVP 面向中国大陆，默认界面和回复使用简体中文，并预留中英文切换能力。房屋历史、房间长期记忆、Property KB、法规合规判断、设备 KB 和租房对比不属于 MVP。MVP 允许低置信度结果提示用户确认，但不要求实现可暂停人工审批；完整 HITL 放入 P1。

### 目标

- 报告中的每个重要风险都能关联 Evidence、置信度和适用的知识来源；纯视觉观察若没有外部知识依据，必须标记为 observation，不得伪装成安全结论。
- 将自由文本 Agent 链路升级为结构化、可验证、可重试的工作流。
- 为后续 Safety、Property Condition、Rental 三种业务模式保留共享底层能力，但 MVP 只交付 Safety Inspection。
- 在不牺牲现有功能的前提下，逐阶段迁移并可回退。

### 首版成功指标

| 指标 | 目标 |
|---|---|
| 报告结构化输出有效率 | ≥99% |
| 关键风险 Evidence 覆盖率 | ≥90% |
| Safety KB 相关问题 Recall@5 | ≥85% |
| 无来源的高风险结论 | 0 个 |
| 端到端报告生成成功率 | ≥95% |

## 2. 背景与问题

### 2.1 当前用户问题

用户希望快速了解房屋视频中的安全风险，但当前结果存在三类不足：

1. 结果更多是模型生成的描述，缺少可追溯证据和权威知识依据。
2. 多 Agent 之间依赖自由 JSON/文本和正则解析，失败后难以定位、重试和测试。
3. 当前 RAG 主要检索 `quick_guide.json` 产品帮助内容，不能回答“为什么危险”“如何整改”“是否涉及法规”等领域问题。

### 2.2 当前技术事实

- 前端：React + Vite。
- 后端：FastAPI + Pydantic。
- AI：YOLOv8、OpenCV/PyTorch、Qwen/DashScope。
- 数据：P00 迁移至 PostgreSQL，PostgreSQL 为最终事实源；pgvector 在 RAG 阶段启用。文件按用户隔离保存。
- 当前 Agent 逻辑实质为 Router → Hazard/Comfort → Compliance/Scoring → Recommendation → ReportWriter。
- 当前指南检索为 BM25，主要服务 GUIDE 类聊天问题。

### 2.3 不解决的代价

- 用户难以信任或复核报告。
- 模型版本、提示词或知识变化会导致结果不可控。
- 新增法规、历史对比和租赁场景时，需要重复改造业务逻辑。
- 无法用稳定数据集衡量检索、检测、Agent 和报告质量。

## 3. 用户与使用场景

### 3.1 用户角色

| 角色 | 目标 | 主要痛点 |
|---|---|---|
| 普通住户 | 发现并处理家庭安全风险 | 不知道风险严重程度和处理顺序 |
| 房东/租客 | 记录入住、退租时房屋状态 | 缺少可比较、可留存的证据 |
| 房产/物业检查人员 | 高效生成检查报告 | 手工整理图片、备注和规范耗时 |
| 系统管理员/知识维护者 | 管理知识来源和版本 | 资料可信度、地区适用性和更新不可控 |

### 3.2 核心用户故事

**US-001：视频检查**
作为住户，我希望上传房屋视频并获得按房间组织的风险报告，以便知道先处理什么；视频处理失败时，我能看到原因并重新上传或重试。

**US-002：可解释风险**
作为住户，我希望点击报告中的风险看到对应帧、区域、置信度和解释，以便判断建议是否可信。

**US-003：知识问答**
作为用户，我希望询问“这个风险为什么存在、如何处理”，系统能引用 Safety KB 回答，而不是凭模型记忆编造。

**US-004：历史比较**
作为房东，我希望比较入住和退租检查，区分原有损伤、新损伤、恶化和已修复问题。

**US-005：合规提示**
作为检查人员，我希望在指定国家/地区后获得带版本和日期的法规参考，并明确声明这不是法律意见；未选择或不支持地区时，系统不得生成合规结论。

**US-006：人工确认**
作为用户，我希望对低置信度识别进行确认或纠正，系统再继续生成报告。

## 4. 产品范围

### 4.1 MVP（Must Have）

- 保留现有视频上传、处理、聊天、报告和 PDF 导出能力；Inspection 可以暂时不绑定 Property。
- 统一 Evidence、Hazard、Recommendation、Report schema。
- 用 LangGraph 表达当前确定性 Agent DAG，支持并行、条件分支、重试和验证。
- Product KB：兼容现有 `quick_guide.json`，支持文档、元数据和引用。
- Safety KB v1：支持审核后的家庭安全资料、混合检索和来源引用。
- 报告展示 Evidence、置信度、引用来源和免责声明。
- 视频最长 30 分钟、单文件最大 2 GB；压测用于验证性能，不用于扩大产品上限。
- P00 建立 GitHub CI：每次 push、Pull Request 和 merge 后都自动执行完整质量检查；CI 失败时禁止合并到受保护主分支。
- 建立离线 Retrieval、Routing、Report 评测数据集。

### 4.2 后续范围（Should/Could Have）

- Property KB、房屋历史、房间长期 Memory、Move-in/Move-out 对比和 Safety Timeline。
- Regulation KB、Device KB、家庭画像和可暂停的人工确认界面。
- 多模型 Provider、独立检索服务和规模化 tracing。

### 4.3 明确不做

- MVP 不提供法律意见、工程鉴定或消防认证。
- MVP 不自动执行维修、报警或联系第三方。
- 不将博客、论坛、营销内容作为 Regulation KB 主来源。
- 不在没有规模指标前同时引入多个向量库、搜索引擎和 Agent 框架。
- 不直接删除现有 AutoGen 流程，必须保留灰度和回退路径。

## 5. 产品体验与流程

```text
登录 → 新建 Inspection → 上传视频/图片 → 处理进度
  → 房间与目标识别 → 风险列表 → 查看证据与来源
  → 生成报告 → 追问/确认 → 导出 PDF → 后续复查
```

### 5.1 检查任务

用户创建 Inspection；MVP 只显示 Safety 模式，Inspection 不要求绑定 Property。用户可填写中国大陆地区信息、房间标签和检查标题，但这些信息只作为当前检查上下文，不形成长期房屋记忆。上传完成后显示处理阶段和失败原因。

### 5.2 报告结果

报告按房间和风险等级组织，至少包含：标题、风险类别、严重程度、置信度、描述、Evidence 帧、建议、来源、适用地区和生成时间。高风险结论必须有 Evidence；不确定结果显示“需要确认”。

### 5.3 RAG 问答

聊天默认绑定当前 Inspection 和用户权限。MVP 只支持 Product/Safety 问题；用户问题先判断是产品帮助还是风险解释，再选择对应 KB。法规、历史和房屋记忆问题明确说明当前版本不支持；没有足够匹配时说明知识库无法确认。

### 5.4 人工确认

MVP 中，当置信度低于阈值、检测涉及重大风险或设备型号不确定时，报告标记为需要确认，用户可以确认/忽略；P1 才暂停工作流并等待确认。所有确认、拒绝和修改都写入审计记录，不覆盖原始模型证据。

## 6. 功能需求

| ID | 需求 | 优先级 | 验收标准 |
|---|---|---|---|
| FR-001 | 创建并执行 Inspection | P0 | 能上传 30 分钟以内、最大 2 GB 的视频并生成唯一任务/报告 |
| FR-002 | 记录结构化 Evidence | P0 | 每条 Evidence 有 id、来源、区域、时间和置信度 |
| FR-003 | LangGraph 状态工作流 | P0 | 节点状态、错误、重试和最终状态可查询 |
| FR-004 | Schema 验证与修复 | P0 | 非法模型输出不会直接进入下游；可重试或标记失败 |
| FR-005 | Product KB 检索 | P0 | 能检索现有指南并返回来源标识 |
| FR-006 | Safety KB 混合检索 | P0 | 支持关键词+向量召回、融合排序和来源过滤 |
| FR-007 | 报告引用证据 | P0 | 每个高风险项至少有一个 Evidence；知识驱动结论必须有 citation，纯观察标记为 observation_only |
| FR-008 | 低置信度处理 | P0 | MVP 显示不确定并允许用户标记；P1 支持暂停/恢复人工确认 |
| FR-009 | 历史 Inspection 查询 | P2 | 仅在 Property 绑定能力启用后，能按用户、房屋、房间和时间检索历史结果 |
| FR-010 | Move-in/Move-out 对比 | P2 | 能输出 New/Existing/Worsened/Resolved/Uncertain |
| FR-011 | Regulation KB | P2 | 结果包含 jurisdiction、version、effective_date、official_url；MVP 不输出法规结论 |
| FR-012 | 质量评测 | P0 | CI 或手动命令可运行检索、schema 和报告评测 |
| FR-013 | 数据导出 | P0 | 用户可以导出自己有权访问的 Inspection、Evidence、Report、Chat 和媒体元数据 |
| FR-014 | 可恢复删除 | P0 | 用户主动删除进入软删除，恢复窗口内可恢复，窗口后异步物理清理 |
| FR-015 | CI/CD 基线 | P00 | push、Pull Request 和 merge 后均执行当前阶段的完整 CI；后续新增数据库、API、工作流、RAG、权限和评测能力时，必须同步增加测试并渐进式升级 Required Checks |

## 7. 技术需求

### 7.1 服务架构

```text
React UI
  ↓ REST/SSE
FastAPI API
  ├─ Inspection Service
  ├─ Knowledge/Retrieval Service
  ├─ LangGraph Workflow Runtime
  ├─ Evidence/Report Service
  └─ Auth & Permission
        ↓
PostgreSQL（P00 迁移后的事实源）
       └─ pgvector（RAG 阶段启用）
Object Storage（视频、帧、PDF）
LLM/VLM Provider Gateway
```

P00 先完成 PostgreSQL 迁移，PostgreSQL 成为最终事实源；随后在 PostgreSQL 上实现结构化 Evidence 和业务迁移，后续启用 pgvector。不得在数据库迁移完成前依赖 PostgreSQL 专属能力，也不得在同一发布中同时切换数据库和工作流。

### 7.2 Workflow State

状态至少包括：`inspection_id`、`user_id`、`run_id`、`locale`、`evidence`、`retrieved_context`、`hazards`、`scores`、`recommendations`、`report`、`errors`、`trace`、`approval_required`、`schema_version`。MVP 的 `approval_required` 只用于提示/标记，P1 才允许暂停并恢复；MVP 不需要 `property_id`。

### 7.3 KB 元数据

每个知识片段至少保存：`kb_type`、`source_id`、`title`、`content`、`source_type`、`trust_tier`、`official_url`、`jurisdiction`、`version`、`effective_date`、`published_at`、`reviewed_at`、`embedding_model` 和权限范围。

### 7.4 API 能力（目标）

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/inspections` | 创建检查任务 |
| POST | `/inspections/{id}/media` | 上传视频/图片 |
| POST | `/inspections/{id}/run` | 启动或恢复工作流 |
| GET | `/inspections/{id}/events` | 获取进度和 trace |
| GET | `/inspections/{id}/evidence` | 获取证据 |
| GET | `/inspections/{id}/report` | 获取结构化报告 |
| POST | `/inspections/{id}/confirmations` | 提交人工确认 |
| POST | `/knowledge/search` | 执行带权限和地区过滤的检索 |
| POST | `/chats/{id}/messages` | 基于上下文问答 |
| POST | `/exports` | 创建用户数据导出任务 |
| GET | `/exports/{id}` | 查询导出状态和限时下载链接 |
| DELETE | `/inspections/{id}` | 软删除 Inspection |
| POST | `/inspections/{id}/restore` | 恢复软删除 Inspection |

实际落地时应兼容现有 `/uploadVideo`、`/processVideoStream`、报告和聊天 API，再通过版本化接口逐步迁移。

## 8. 数据与权限

核心实体：`User`、`Inspection`、`MediaAsset`、`Evidence`、`Hazard`、`Recommendation`、`Report`、`KnowledgeSource`、`KnowledgeChunk`、`UserConfirmation`、`WorkflowRun`、`ExportJob`。P00/MVP 不创建 Property、Repair 和房屋历史实体；未来启用房产绑定时再新增 Property 模块。

- 用户只能访问自己拥有或被授权的 Property、Inspection、媒体、聊天和报告；共享关系必须有显式记录、角色和撤销时间。
- MVP 不启用 Property KB；公共 Product/Safety KB 与用户检查数据分离存储和检索，不能跨用户泄露。
- 原始视频、图片和模型输出保留来源链路；用户删除进入可恢复软删除，不立即物理删除，恢复窗口结束后才清理对象存储和索引。
- 用户可以导出自己有权访问的业务数据；导出任务异步生成，下载链接限时有效。
- API Key、家庭成员信息和位置等敏感数据不得写入普通日志。
- 报告标明生成时间、模型版本、Prompt/schema 版本、知识版本和“辅助判断、非专业/法律意见”声明。法规未匹配到有效辖区时只能显示“未评估合规性”。

## 9. 非功能需求

| 类别 | 要求 |
|---|---|
| 性能 | 普通文本问答 P95 ≤ 5 秒（不含外部模型极端延迟）；进度处理采用异步流；视频最长 30 分钟且不超过 2 GB |
| 可靠性 | 临时错误可重试且有上限；任务状态可恢复；报告生成失败不丢失 Evidence；重复请求不产生重复 run |
| 可观测性 | 记录 workflow run、节点耗时、模型调用、token/成本、检索结果和错误 |
| 安全 | 鉴权、对象归属校验、上传类型/大小校验、密钥隔离和权限过滤 |
| 可扩展性 | Agent 通过 schema 和 Provider 接口解耦；KB 可插拔；保留 API 兼容层 |
| 可用性 | 结果页面展示来源、证据和不确定性，不把模型推测伪装成事实 |

## 10. 评测与验收

### 10.1 离线评测集

在 `tests/evals/` 建立：

- `retrieval_dataset.json`：问题、正确 KB、相关来源和地区。
- `hazard_dataset.json`：Evidence、风险类别、严重程度和人工标签。
- `routing_dataset.json`：问题类型与目标 workflow 路径。
- `report_dataset.json`：输入证据、期望引用、建议和禁止结论。

### 10.2 发布门槛

- 所有 P0 schema 和 API 测试通过。
- 无越权访问和跨用户检索结果。
- P0 场景端到端成功率达到 95%。
- 高风险报告没有无证据结论。
- Safety KB 的来源可追溯且通过人工抽样审核。
- 新旧流程在同一测试集上的关键指标不低于基线；否则暂停迁移。

## 11. 里程碑与交付物

| 阶段 | 预计周期 | 交付物 |
|---|---:|---|
| P00-A CI/CD 基线 | 1 周 | GitHub Actions、当前 MySQL 质量门禁、Docker 构建、测试报告和分支保护 |
| P00-B 数据库迁移 | 1–2 周 | PostgreSQL Docker service、schema、离线导入、校验、旧 API 回放和回退方案 |
| P00-C PostgreSQL CI 门禁 | 0.5–1 周 | PostgreSQL 集成测试、Compose 配置和 Required Check 切换 |
| P0 基线 | 1 周 | 架构盘点、数据字典、评测集、回退方案（在 P00 后） |
| P0 工作流 | 2–3 周 | LangGraph 图、State、schema、Validator、兼容 API |
| P0 RAG | 2–3 周 | Product/Safety KB、索引、混合检索、引用报告 |
| P1 感知与历史 | 3–5 周 | Evidence Store、Property 数据模型、时间对比原型 |
| P2 合规与租赁 | 4–6 周 | Regulation/Device KB、Move-in/Move-out、HITL |
| 稳定化 | 持续 | 评测、追踪、成本优化、灰度和运营工具 |

周期按一名后端/AI 工程师、一名全栈工程师和兼职产品/测试投入估算，实际以基线评估后调整。

## 12. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 模型幻觉或错误风险判断 | 高 | Evidence 强制关联、来源引用、结构化验证和人工确认 |
| 法规过期或地区错误 | 高 | jurisdiction/version/effective_date 强过滤，Regulation KB 仅允许审核来源 |
| 迁移破坏现有功能 | 高 | 兼容旧 API、双流程对比、灰度开关和回退 |
| RAG 召回不佳 | 中 | BM25+向量混合、Rerank、评测集和人工审核 |
| 推理成本过高 | 中 | 规则优先、关键帧选择、模型分级、缓存和并行控制 |
| 用户隐私泄露 | 高 | 用户级权限、对象存储隔离、日志脱敏和删除链路 |
| 范围蔓延 | 中 | MVP 只交付 Product/Safety KB 和核心工作流，每阶段设发布门槛 |

## 13. 决策与待确认事项

以下事项已确认，作为本版本冻结基线：

1. MVP 使用中国大陆市场和简体中文；中英文切换作为后续兼容能力。
2. P00 先完成 MySQL → PostgreSQL，PostgreSQL 为最终事实源，pgvector 后置。
3. Safety KB 的首批主题和允许使用的资料来源。
4. 报告是否需要面向物业/租赁场景的正式证据格式。
5. 目标部署规模、模型预算和共享策略；数据保留周期采用技术文档中的 MVP 建议值，正式上线前再确认。

## 14. Definition of Done

本项目阶段性完成的标准是：用户能够创建一次检查、上传媒体、看到处理进度，获得一份由结构化 Evidence 支撑的报告；报告中的风险可以被追问，回答来自正确 KB 且带有来源；异常任务能够重试或恢复；私有数据严格隔离；核心质量指标有可重复的评测结果。
