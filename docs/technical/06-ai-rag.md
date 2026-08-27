# AI、Evidence 与 RAG 技术文档

## 1. Perception pipeline

```text
Video（≤30 分钟、≤2 GB）→ bounded sampling/keyframes
      → YOLO detection → tracking
      → VLM scene analysis/OCR → evidence fusion
```

Evidence 是唯一进入 Risk Engine 的视觉事实层。原始模型响应可保存用于调试，但不得直接作为报告字段。

当前代码的 `select_representative_images_by_room(..., max_frames=15)` 代表最多保留 15 张代表图；它发生在原始帧抽取和过滤之后，不能替代原始抽帧限流。P0 应增加原始帧数量、磁盘空间和单任务处理时长上限，避免 30 分钟视频按 1 FPS 产生约 1800 张中间文件。

## 2. Evidence schema

```json
{"id":"uuid","source_type":"yolo|vlm|ocr|user|history","object_type":"stove","room":"kitchen","bbox":[0.1,0.2,0.4,0.6],"timestamp":43.2,"observation":"flammable item near stove","confidence":0.91,"attributes":{}}
```

## 3. 五类 KB

Product 来自项目文档；Safety 来自权威安全机构、行业组织和审核资料；Regulation 来自政府/标准原文；Property 来自用户私有历史；Device 来自厂商资料。每类 KB 单独维护权限、来源等级和更新策略。

## 4. Ingestion

```text
Source registry → fetch/upload → parse → clean
→ structure-aware chunk → metadata → deduplicate
→ embed → keyword/vector index → human review → publish
```

法规按 article/section/clause 切分并保存版本；Property 结构化实体优先入库，文本仅作为补充索引。

## 5. Retrieval

```text
query classify/rewrite
 → permission + jurisdiction filter
 → BM25 + vector top-k
 → RRF fusion
 → rerank
 → freshness/trust filter
 → context builder
```

检索返回来源，不只返回文本。Context Builder 限制 token、去重、保留 section 上下文并标注 `source_id`。

## 6. Risk engine

明显空间关系和阈值规则先执行；复杂场景调用结构化 LLM/VLM。每项风险必须有 `evidence_ids`。纯观察使用 `observation_only=true`；知识驱动建议必须有 `citation_ids`，且 Citation 必须支持对应建议。低置信度在 MVP 以不确定措辞和用户标记结束，P1 才进入可恢复人工确认。

## 7. Prompt 与模型治理

Prompt 按版本存储，模型调用记录 provider、model、temperature、token、latency 和 schema version。禁止将用户私有内容混入公共检索索引。模型切换必须在离线评测集上与基线比较。外部文档中的指令只能作为数据，不能改变系统规则、权限或工具调用。
