# Qwen 统一模型栈技术设计

## 1. 文档目的

本文档定义 SafeScan 统一使用 Qwen 模型栈时的生产技术方案。统一范围包括文本生成、视觉理解、OCR、Embedding 和 Rerank；统一不意味着所有任务使用同一个模型，而是通过统一的模型网关、任务路由、版本治理和评测体系使用不同能力等级的 Qwen 模型。

本文档以当前仓库的 React + FastAPI + AutoGen + YOLO/OpenCV + DashScope 基线为约束。当前 `quick_guide.json` 仍是 BM25 产品指南检索；完整向量 RAG 和 pgvector 按既有 P0 路线实施。

## 2. 设计原则

1. 规则和确定性视觉算法优先，LLM/VLM 只处理需要语义理解或复杂推理的部分。
2. LLM、VLM、OCR、Embedding、Rerank 使用独立接口，不在 Agent 中硬编码具体模型。
3. 生产模型使用可追溯的固定版本，不使用 `latest` 作为生产基线。
4. 视觉事实、风险判断、知识引用和最终报告分层保存，模型不得跨层隐式改写事实。
5. 高风险任务升级到高能力模型，普通任务使用低成本模型。
6. 模型、Prompt、Schema、知识库和向量索引均必须可回放、可比较、可回滚。

## 3. 模型目录

截至 2026-08，百炼官方模型目录中，`qwen3.8-max` 支持文本、图像、视频、长上下文、Function Calling 和结构化输出；`qwen3.7-plus` 和 `qwen3.7-flash` 支持文本、图像、视频以及结构化输出。模型能力和可用区域以官方目录为准。

| 能力 | 生产候选 | 主要用途 | 默认策略 |
|---|---|---|---|
| Fast | `qwen3.7-flash` | 路由、分类、查询改写、简单摘要 | 高并发默认 |
| Standard | `qwen3.7-plus` 固定快照 | 风险解释、普通报告、视觉分析 | 主力默认 |
| Reasoning | `qwen3.8-max` | 高风险、多证据、冲突判断 | 条件升级 |
| Vision | `qwen3.7-plus` 固定快照 | 图片、视频帧、空间关系 | 视觉默认 |
| OCR | `qwen3.5-ocr` 或 `qwen-vl-ocr` | 铭牌、说明书、表格和标签 | 专项调用 |
| Text Embedding | `text-embedding-v4` | Product/Safety/Regulation 文本 RAG | MVP 默认 |
| Text Rerank | `qwen3-rerank` | 文本召回结果排序 | RAG 默认 |
| Multimodal Embedding | `qwen3-vl-embedding` | 图文联合检索 | P1/P2 |
| Multimodal Rerank | `qwen3-vl-rerank` | 图文/图视频结果排序 | P1/P2 |

官方视觉文档说明，`qwen3.7-plus` 支持图像、视频、结构化输出和 Function Calling；视觉模型的最大视频时长、图片数量和分辨率会随模型版本和部署区域变化，不应在代码中写死为单一平台上限。

## 4. 任务路由

### 4.1 业务等级

| 业务等级 | 进入条件 | 模型 | 思考模式 |
|---|---|---|---|
| L0 | 检测类别、距离阈值、权限、状态机 | 规则/YOLO/SQL | 不适用 |
| L1 | 路由、分类、改写、摘要、低风险 FAQ | `qwen3.7-flash` | 关闭 |
| L2 | 普通风险解释、整改建议、报告编排 | `qwen3.7-plus` | 按任务配置 |
| L3 | 严重风险、多 Evidence、冲突或不确定结论 | `qwen3.8-max` | 开启 |
| VL | 图片、关键帧、视频场景理解 | `qwen3.7-plus` | 按视觉任务配置 |

### 4.2 推荐路由表

```text
query_classification       -> L1
query_rewrite              -> L1
product_qa                 -> L1/L2
vision_frame_analysis      -> VL
ocr                        -> OCR
normal_hazard_reasoning    -> L2
critical_hazard_reasoning  -> L3
report_generation          -> L2
complex_report_validation  -> L3
text_embedding             -> Embedding
text_rerank                -> Rerank
```

升级到 L3 的条件至少包括：涉及燃气、火灾、电气、儿童或老人；需要联合三个及以上 Evidence；YOLO 与 VLM 结论冲突；用户要求解释严重风险；知识片段冲突；或 L2 输出未通过业务校验。

## 5. Provider Gateway

### 5.1 接口

```python
class LLMProvider:
    async def generate(self, messages, *, model, temperature, timeout): ...
    async def generate_structured(self, messages, *, schema, model, timeout): ...

class VisionProvider:
    async def analyze_image(self, image, *, prompt, schema, model): ...
    async def analyze_video(self, video, *, prompt, schema, model): ...

class EmbeddingProvider:
    async def embed_documents(self, texts, *, model, dimension): ...
    async def embed_query(self, text, *, model, dimension): ...

class RerankProvider:
    async def rerank(self, query, documents, *, model, top_n): ...
```

Agent 只传递 `task_type`，不传递平台模型名：

```python
result = await model_gateway.generate_structured(
    task_type="critical_hazard_reasoning",
    messages=messages,
    schema=HazardDecisionSchema,
)
```

Gateway 负责模型选择、参数、超时、重试、降级、调用记录和成本统计。当前 `backend/app/agents/autogen_agent_base.py` 直接创建 `DashScopeChatCompletionClient`，应逐步迁移到该网关；AutoGen 仍可作为工作流 Agent 运行时。

### 5.2 注册表

```python
MODEL_REGISTRY = {
    "fast": {"model": "qwen3.7-flash", "vision": False, "thinking": False},
    "standard": {"model": "qwen3.7-plus-2026-05-26", "vision": True, "thinking": True},
    "reasoning": {"model": "qwen3.8-max", "vision": True, "thinking": True},
    "ocr": {"model": "qwen3.5-ocr", "vision": True, "thinking": False},
    "embedding": {"model": "text-embedding-v4", "dimension": 1024},
    "rerank": {"model": "qwen3-rerank"},
}
```

注册表必须支持 primary、canary 和 fallback；模型调用记录实际生效的模型名，不记录逻辑等级代替模型名。

## 6. 视觉和视频处理

### 6.1 Pipeline

```text
Video -> 场景分段 -> 限流抽帧 -> YOLO 检测/跟踪
      -> 房间代表帧 -> Qwen Vision -> Evidence
      -> 规则 Risk Engine -> L2/L3 风险推理
```

YOLO/OpenCV 负责目标检测、框、类别、置信度、跟踪和基础空间计算；Qwen Vision 负责房间语义、物体关系、场景上下文和不确定性说明。Qwen Vision 不替代确定性检测，也不直接写入最终风险字段。

### 6.2 Vision 输出

所有视觉输出必须符合 Evidence 输入 Schema：

```json
{
  "source_type": "vlm",
  "room": "kitchen",
  "observation": "flammable item appears close to stove",
  "confidence": 0.88,
  "timestamp": 43.2,
  "bbox": [0.12, 0.30, 0.60, 0.80],
  "observation_only": true,
  "attributes": {"needs_risk_reasoning": true}
}
```

视觉 Prompt 只能要求可观察事实，不得要求模型直接给出法规结论。低质量、遮挡或证据不足时必须输出 `uncertain`。

### 6.3 OCR

设备型号、警示标签、说明书和表格优先进入 OCR 专用模型；OCR 结果需保存原始图片引用、文本区域、置信度和语言。OCR 结果只能作为 Evidence 或 KB ingestion 的输入，不能未经校验直接成为设备型号事实。

## 7. Embedding、Rerank 与 RAG

### 7.1 默认选择

MVP 文本知识库使用 `text-embedding-v4`，固定 1024 维、余弦相似度和 L2 归一化。官方文档列出的该模型支持 64–2048 维，最大输入长度 8192 Token；生产固定维度有利于 pgvector schema、索引和回滚稳定。

文本 RAG 使用 `qwen3-rerank` 对 BM25 和向量召回结果重排序。图片/视频进入向量检索属于 P1/P2，不与 MVP 文本索引混用。

### 7.2 Pipeline

```text
Document -> parse -> clean -> structure-aware chunk
         -> metadata -> deduplicate -> text-embedding-v4 -> pgvector

Query -> qwen3.7-flash rewrite/classify
      -> permission/jurisdiction filter
      -> BM25 Top-30 + Vector Top-30
      -> RRF Top-20 -> qwen3-rerank Top-5/10
      -> context builder -> qwen3.7-plus/qwen3.8-max
```

KB 类型保持隔离：Product、Safety、Regulation、Property、Device 分别治理。Property KB 以 SQL 和结构化过滤为主；Regulation KB 必须先按 jurisdiction、version 和 effective_date 过滤，再做语义召回。

### 7.3 向量元数据

知识片段至少保存：

```text
kb_type, source_id, title, content, source_type, trust_tier,
official_url, jurisdiction, version, effective_date, reviewed_at,
embedding_provider, embedding_model, embedding_model_version,
embedding_dimension, embedding_normalization, vector_index_version,
permissions, embedded_at
```

### 7.4 Embedding 变更

Embedding 模型、维度或归一化方式变化时，禁止原地覆盖：

```text
旧索引 v1 -> 全量生成向量 v2 -> 新 pgvector 索引
          -> 离线 Recall/MRR/Citation 评测
          -> Shadow Retrieval -> 灰度 -> 切换
```

旧索引至少保留一个回滚窗口。模型调用、知识版本和索引版本必须在报告中可追溯。

## 8. Prompt、Schema 和安全边界

Prompt 分为 Vision、Risk、Recommendation、Report 四类。Report 模型只能聚合已经验证的 Evidence、Hazard 和 Citation，不得重新观看视频或新增风险。

每次模型输出必须经过：

```text
JSON extraction -> Pydantic schema -> business validation -> persistence
```

业务校验包括：风险必须有 `evidence_ids`；建议必须有 `citation_ids`；置信度必须在 0–1；法规结论必须有 jurisdiction 和知识版本；无来源时输出不确定；外部文档指令只能作为数据，不能改变系统权限和工具规则。

## 9. 配置

生产配置建议如下：

```env
QWEN_API_KEY=...
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL_FAST=qwen3.7-flash
QWEN_MODEL_STANDARD=qwen3.7-plus-2026-05-26
QWEN_MODEL_REASONING=qwen3.8-max
QWEN_MODEL_VISION=qwen3.7-plus-2026-05-26
QWEN_MODEL_OCR=qwen3.5-ocr
QWEN_EMBEDDING_MODEL=text-embedding-v4
QWEN_EMBEDDING_DIMENSION=1024
QWEN_RERANK_MODEL=qwen3-rerank
QWEN_MODEL_CANARY_ENABLED=false
```

`ALIBABA_MODEL_L1/L2/L3/VL` 可保留兼容读取，但新实现应优先使用按任务命名的配置。生产不使用 `*-latest`；升级必须改版本、跑评测、灰度并登记变更。

## 10. 可观测性

每次调用记录：`request_id`、`workflow_run_id`、`node`、`task_type`、`provider`、`model`、`model_version`、`prompt_version`、`schema_version`、`knowledge_version`、`embedding_version`、输入输出 Token、延迟、重试次数、状态和错误码。

不得把视频、图片、完整模型原始响应或密钥写入普通日志；原始响应如需调试，必须按权限和保留期限存储。

## 11. 评测与发布门槛

评测集至少覆盖视觉关系、OCR、风险等级、RAG 召回、引用准确率、无答案、Prompt Injection 和 JSON 合法率。

发布门槛：新模型的结构化通过率、高风险召回率、Citation Precision、Groundedness 不得低于基线；幻觉率、P95 延迟和单位任务成本不得超过预算阈值。先 Shadow，再按任务 5%/25%/100% 灰度；任何严重风险回归都自动回退到 primary。

## 12. 实施顺序

1. 建立模型注册表和 Gateway，保留现有 DashScope 客户端作为适配器。
2. 将 `autogen_agent_base.py` 的直接模型选择改为任务类型路由。
3. 接入固定版本的 Qwen Vision，统一 Evidence Schema 和业务校验。
4. 接入 `text-embedding-v4`、pgvector、BM25/RRF 和 `qwen3-rerank`。
5. 将高风险节点接入 `qwen3.8-max`，普通任务使用 `qwen3.7-plus`，轻量任务使用 `qwen3.7-flash`。
6. 建立离线评测、Shadow Run、灰度和回滚开关。
7. P1/P2 再评估 `qwen3-vl-embedding` 与 `qwen3-vl-rerank` 的图文联合检索。

## 13. 参考资料

- [阿里云百炼文本生成模型](https://help.aliyun.com/zh/model-studio/text-generation-model)
- [Qwen3.8-Max 模型信息](https://help.aliyun.com/zh/model-studio/qwen3-8-max)
- [阿里云百炼视觉理解](https://help.aliyun.com/zh/model-studio/vision-model/)
- [阿里云百炼向量与重排序](https://help.aliyun.com/zh/model-studio/embedding-rerank-model)
