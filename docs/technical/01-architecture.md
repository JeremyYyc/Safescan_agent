# 技术架构总览

## 1. 目标

将当前 React + FastAPI + MySQL + YOLO/Qwen + AutoGen 原型演进为证据驱动、可恢复、可观测的 Property Inspection 平台。

## 2. 逻辑分层

```text
Frontend
  ↓ REST / SSE
API & Auth Layer
  ↓
Application Services
  ├─ Inspection Service
  ├─ Evidence Service
  ├─ Report Service
  ├─ Knowledge/Retrieval Service
  └─ Chat Service
  ↓
Workflow Runtime (LangGraph)
  ├─ Perception
  ├─ Risk/Compliance
  ├─ Recommendation
  └─ Validation/HITL
  ↓
Repositories
  ├─ PostgreSQL（P00 迁移后的事实源）
  │    └─ pgvector（RAG 阶段启用）
  └─ Object Storage（视频、帧、PDF）
```

## 3. 关键设计决策

- 使用 LangGraph 表达已有 DAG；保留旧 Orchestrator 作为回退实现。
- 使用 Pydantic 作为边界 schema；业务层不消费自由文本。
- 使用 Service/Repository 分层，API 层不直接写数据库。
- RAG 是 Knowledge Platform，不是单独 VectorDB；Product/Safety/Regulation/Property/Device 分开治理。
- P00 先完成 MySQL → PostgreSQL；数据库迁移独立于 LangGraph/RAG 发布，PostgreSQL 是最终事实源，pgvector 后置启用。

## 4. 端到端数据流

```text
Upload → MediaAsset → Inspection
       → Perception → Evidence
       → Query Planner → KB Retrieval
       → Hazard/Compliance/Score
       → Recommendation → Report Validator
       → Report + citations → UI/PDF
```

每一步写入 `workflow_runs` 和持久化 `workflow_events`；任务中断后从 checkpoint 恢复，而不是重新处理全部视频。媒体上传、完整性校验和病毒扫描通过后才能启动工作流。

## 5. 模块边界

| 模块 | 负责 | 不负责 |
|---|---|---|
| API | 鉴权、校验、协议转换 | 模型推理和复杂 SQL |
| Inspection Service | 任务生命周期、所有权 | 具体视觉算法 |
| Perception | 检测、跟踪、关键帧和 Evidence | 合规结论 |
| Retrieval | 查询改写、召回、排序、引用 | 生成最终建议 |
| Risk Engine | 规则和模型推理 | 直接修改用户数据 |
| Report | 聚合、验证、导出 | 重新推理视觉结果 |

## 6. 生命周期边界

`Property` 是长期资源；`Inspection` 是一次输入快照；`WorkflowRun` 是一次执行尝试；`Report` 是某次成功 run 的版本化产物；`Chat` 是围绕用户/Inspection 的会话。重新处理必须创建新 run 和新报告版本，不覆盖原始 Evidence。

## 7. 可扩展性

Provider 接口隔离 LLM/VLM/Embedding；KnowledgeSource 接口隔离文件、网页、用户数据；Workflow 节点通过 typed state 通信。新增 Rental 模式应复用 Inspection/Evidence/Report，而不是复制一套 Agent。
