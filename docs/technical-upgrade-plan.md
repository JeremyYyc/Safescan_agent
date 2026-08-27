# SafeScan Agent 技术扩展与升级方案

## 1. 文档定位

本文将“技术扩展与升级建议”整理为可执行的演进计划。当前实施基线为中国大陆、简体中文、Safety Inspection MVP；目标不是为了引入更多框架，而是把现有的“YOLO/视觉模型 + Qwen + AutoGen + 报告生成”原型，逐步升级为具备证据链、知识检索、状态工作流、历史记忆和评测能力的 AI Property Inspection Platform。

当前项目已有基础：React 前端、FastAPI 后端、MySQL、Docker、YOLOv8、OpenCV/PyTorch、Qwen/DashScope、AutoGen、多 Agent 报告流程，以及基于 `quick_guide.json` 的轻量 BM25 产品指南检索。

## 2. 目标架构

```text
Video / Image / User Input
            ↓
Perception Layer
 YOLO · VLM · OCR · Tracking
            ↓
Evidence Layer
   统一结构化 Evidence
            ↓
Knowledge Platform
 Safety · Regulation · Product · Property · Device
            ↓
Risk & Reasoning Engine
 规则引擎 + LLM/VLM 推理
            ↓
LangGraph Workflow
            ↓
Grounded Report / Chat / Timeline / Alerts
```

产品边界可从“家庭安全视频分析”扩展为三个模式：

- Home Safety Inspection：火灾、电气、燃气、跌倒、儿童和老人安全。
- Property Condition Inspection：裂缝、霉斑、渗水、墙面、地板、门窗和设备状态。
- Rental Inspection：Move-in/Move-out 对比、损伤证据和整改记录。

## 3. 主要重构原则

### 3.1 AutoGen 迁移到 LangGraph

当前实际执行结构已经是确定性的 DAG：

```text
Router → Hazard/Comfort → Compliance/Scoring → Recommendation → ReportWriter
```

因此使用 LangGraph `StateGraph` 表达状态、并行节点、条件边、重试、检查点和人工介入更合适。建议的流程：

```text
START
  ↓
EvidenceBuilder
  ↓
ContextRouter
  ├─ Hazard Analysis
  └─ Comfort Analysis
          ↓
   Safety Retrieval / Regulation Retrieval
          ↓
   Compliance + Scoring
          ↓
   Recommendation
          ↓
   ReportWriter
          ↓
   Validator ── invalid → Repair/Retry
          ↓
         END
```

Router 不应把所有判断交给 LLM。能由规则确定的内容（例如是否存在儿童/老人、是否识别到楼梯或燃气设备）使用确定性条件边；复杂语义判断再调用模型，以降低成本并提高可测试性。

### 3.2 统一结构化输出

逐步移除依赖自由文本、`json.loads()` 和正则提取 JSON 的链路。为 Evidence、Hazard、Compliance、Score、Recommendation、Report 定义 Pydantic schema，并执行：

```text
LLM/VLM → Schema Validation → Repair/Retry → 下游节点
```

示例字段：

```json
{
  "id": "hazard-001",
  "category": "fire",
  "severity": 4,
  "confidence": 0.87,
  "evidence_ids": ["evidence-231"],
  "knowledge_source_ids": ["source-42"]
}
```

### 3.3 先形成 Evidence，再进行推理

统一 Evidence Model，使 YOLO、VLM、OCR、用户标注、传感器和历史记录都能进入同一个证据层：

```text
Evidence {
  id, source_type, object_type, region, bbox,
  observation, confidence, timestamp, attributes
}
```

这样报告可以回答“依据哪一帧、哪个区域、哪个模型结果得出结论”，而不是只生成无法追溯的自然语言。

## 4. Knowledge Platform 与 RAG 设计

当前 `backend/app/knowledge/guide.py` + `quick_guide.json` 是 Product KB 的起点，使用 BM25 检索 SafeScan 使用指南。它可以称为轻量 retrieval-augmented prompt，但还不是完整的多知识库 RAG。

### 4.1 五类知识库及资源来源

| KB | 主要回答 | 资源来源 | 属性 |
|---|---|---|---|
| Product KB | SafeScan 怎么使用 | README、正式文档、FAQ、API/功能说明、产品更新日志 | 项目自身维护 |
| Safety KB | 什么情况危险、为什么、如何处理 | 政府安全机构、消防/电气/公共卫生机构、行业协会、论文和审核过的专业资料 | 公共知识 |
| Regulation KB | 是否涉及法规、标准或合规要求 | 政府官网、法规数据库、建筑/消防/电气标准、租赁法和官方标准机构 | 必须按 jurisdiction、版本和生效日期管理 |
| Property KB | 这套房过去发生过什么 | 用户视频/图片、AI Evidence、历史 inspection/report、缺陷、维修、房屋信息和用户输入 | 用户私有数据 |
| Device KB | 某设备如何使用、维护或是否召回 | 厂商说明书、官方维护指南、召回公告和产品安全文档 | 以制造商资料为主 |

核心边界：Safety KB 解释风险，Regulation KB 解释合规，Property KB 保存用户房屋历史，Product KB 解释产品用法。不能把它们不加区分地放入一个向量库。

### 4.2 来源可信度与治理

建议记录 `source_type`、`trust_tier`、`official_url`、`jurisdiction`、`version`、`effective_date`、`published_at`、`reviewed_at` 和 `license`。

```text
Tier 1：政府、法律、官方标准
Tier 2：官方机构、行业协会、制造商
Tier 3：大学、论文、专业研究
Tier 4：审核通过的专业文章
```

检索排序不能只看 embedding 相似度，应综合：

```text
相关度 + 可信度 + 地区匹配 + 时间有效性 + 知识库权限
```

Regulation KB 后续必须按国家/地区保存；MVP 目标市场为中国大陆且不输出法规结论。未来启用时再建立 `CN/省/市` 等 jurisdiction 层级，避免用错误地区回答用户。

### 4.3 检索技术路线

第一阶段先完成 MySQL → PostgreSQL 迁移，PostgreSQL 成为最终事实源；RAG 阶段再启用 pgvector。不要同时引入 MySQL、Qdrant、Elasticsearch 等多个系统，独立向量数据库只有在规模、延迟或过滤需求证明必要时才评估。

目标 pipeline：

```text
Document → Parse → Clean → Semantic/structural chunk
         → Metadata → Embedding → Index

Query → Query Understanding/Rewrite
      → Keyword/BM25 + Vector Retrieval
      → RRF/融合 → Rerank → Context Filter → LLM
```

Safety 文档可按语义章节切分；法规应尽量保留 chapter/section/article/clause 层级，不能简单按固定字数切断上下文；Property KB 则以结构化数据库为主，结合 SQL 过滤和语义检索，而不是把所有历史数据当普通文本切块。

### 4.4 RAG 应进入报告链路

RAG 不应只服务聊天问答。建议 Hazard Agent 先产出风险候选，再查询 Safety KB；涉及法规时查询 Regulation KB；Recommendation Agent 输出带证据和来源的建议。报告至少保存：风险、证据、引用来源、置信度、适用地区和知识版本。

## 5. AI 能力扩展

### 5.1 视频理解

将“逐帧检测”升级为：

```text
Scene Segmentation → Object Detection → Tracking
                  → Key-frame Selection → VLM Understanding
                  → Evidence Fusion
```

例如将“检测到儿童”和“检测到热锅”结合为带场景上下文的风险，而不是两个孤立标签。

### 5.2 确定性 Risk Engine

明显、可解释的规则优先由规则引擎完成，例如目标类型、空间关系和距离阈值满足条件时直接产生候选风险；复杂或不确定场景才交给 LLM/VLM。最终形成：

```text
Deterministic Rules + LLM/VLM Reasoning → Risk Engine
```

### 5.3 Temporal Reasoning 与 Property Memory

建立 Property、Inspection、Evidence、Defect、Repair 等实体，支持：

- 比较不同时间的扫描结果：New、Existing、Improved、Worsened、Resolved、Uncertain。
- 查询某房间历史缺陷和整改记录。
- 生成 Home Safety Timeline 和风险趋势。
- 将用户家庭画像从若干布尔值升级为住户年龄、行动能力、宠物、房型、设备和风险偏好。

RAG 与 Memory 分开：Thread Memory 保存当前对话，User/Property Memory 保存长期事实，Safety History 保存历史风险和整改，公共 KB 保存外部知识。

### 5.4 Human-in-the-loop

对低置信度识别、高风险建议和无法确认的设备触发人工确认。LangGraph checkpoint 允许用户确认后从中断节点继续，而不必重新执行整条流程。

### 5.5 LLM Provider 抽象

以现有 `llm_registry.py` 为基础，抽象统一接口：

```text
generate() · generate_structured() · embed() · vision()
```

Agent 不直接绑定 DashScope；后续可插入 Qwen、OpenAI、本地模型等 Provider。

## 6. 分阶段实施计划

### Phase 0：基线与安全边界

- 保留当前功能和 API 行为，补充架构文档与数据流图。
- 盘点 AutoGen、Agent 输出、数据库实体和现有 `guide.py` 检索逻辑。
- 建立 AI 评测样例和可重复测试数据。

### Phase 0A：P00，数据库迁移

- 新建 PostgreSQL 数据库。
- 离线迁移现有业务表，完成行数、checksum、外键和业务回放校验。
- PostgreSQL 切换为唯一事实源，观察稳定后再进入 P0。

### Phase 1：P0，先做可控的核心重构

- 定义 Pydantic schema 和 Evidence Model。
- 将当前 Agent DAG 映射为 LangGraph；保留旧流程作为回退路径。
- 把 Product KB 从 `quick_guide.json` 扩展为可带 metadata 的文档集合。
- 实现混合检索接口，先支持 BM25，预留 embedding/rerank 接口。
- 将 Safety KB v1 接入 Hazard/Recommendation，并让报告保存引用来源。

### Phase 2：P1，提升感知和个性化

- 场景分段、目标跟踪、关键帧选择和 Evidence 融合。
- Property/Inspection/Evidence/Defect/Repair 数据模型。
- 历史报告对比、风险趋势和家庭画像。
- LLM Provider 抽象与结构化输出修复机制。

### Phase 3：P2，合规与产品化

- 建立按 jurisdiction 管理的 Regulation KB 及版本治理。
- 建立 Device KB 和厂商文档引用。
- 加入 Human-in-the-loop、权限隔离、审计日志和数据删除策略。
- 支持 Rental Move-in/Move-out 报告和新旧损伤对比。

### Phase 4：规模化与运营

- 根据 chunks 规模、延迟和过滤复杂度决定是否拆分独立 Retrieval Service 或迁移 Qdrant。
- 增加 tracing、线上反馈闭环和知识库更新流水线。
- 对索引、模型、检索、Agent 和报告质量做持续评测。

## 7. 评测与验收指标

```text
Retrieval：Recall@K、MRR、Hit Rate、引用正确率
Detection：Precision、Recall、mAP、跨帧稳定性
Agent：路由正确率、schema 有效率、重试率、节点耗时
Report：groundedness、evidence coverage、幻觉率、建议相关性
Product：端到端成功率、P95 延迟、成本、人工确认率
```

建议建立 `tests/evals/`，至少包含 `retrieval_dataset.json`、`hazard_dataset.json`、`routing_dataset.json` 和 `report_dataset.json`。第一阶段用 pytest + 自定义评测即可，后续再接入专门的 tracing/evaluation 平台。

## 8. 暂不做的事项

- 不为展示技术而同时引入多个向量数据库、搜索引擎和 Agent 框架。
- 不把未经审核的博客、论坛、营销文章作为 Safety/Regulation 主干来源。
- 不让模型直接给出无司法辖区和版本信息的法规结论。
- 不把 Property 私有数据与公共知识混在同一个权限域。
- 不在没有基线、数据集和回退方案的情况下直接替换全部生产链路。

## 9. 最终判断标准

每项技术选型都应回答三个问题：

1. 它是否解决当前真实瓶颈，而不是增加名义上的技术复杂度？
2. 它是否能留下结构化证据、可测试接口和可回退路径？
3. 它是否支持未来的 Safety、Property 和 Rental 三类业务共用？

SafeScan 的核心竞争力不应是“用了多少 AI 框架”，而应是：**多模态证据能够被可靠提取，风险判断能够被知识和规则支撑，报告能够解释、追溯，并随房屋历史持续演进。**
