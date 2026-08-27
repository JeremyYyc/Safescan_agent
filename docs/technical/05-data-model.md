# 数据模型与迁移文档

## 1. 核心实体

```text
User 1──N Inspection 1──N MediaAsset
Inspection 1──N Evidence 1──N Hazard
Hazard 1──N Recommendation
Report 1──N ReportCitation ──N KnowledgeChunk ──1 KnowledgeSource
Inspection 1──N WorkflowRun 1──N WorkflowEvent
Hazard 1──N UserConfirmation
（后续 Property 版本再增加 Property、Defect、Repair）
```

## 2. 关键字段

| 表 | 必要字段 |
|---|---|
| properties | id, owner_id, address_region, metadata, created_at（后续版本） |
| inspections | id, owner_id, mode, status, locale, region, started_at, completed_at, deleted_at, deleted_by |
| media_assets | id, inspection_id, owner_id, object_key, media_type, checksum, scan_status, duration_seconds, size_bytes |
| evidence | id, inspection_id, media_asset_id, source_type, room, bbox, timestamp, observation, confidence |
| hazards | id, inspection_id, category, severity, confidence, status, evidence_ids |
| recommendations | id, hazard_id, priority, action, rationale, citation_ids |
| reports | id, inspection_id, schema_version, payload, model_info, created_at |
| knowledge_sources | id, kb_type, title, source_type, trust_tier, official_url, jurisdiction, version, effective_date |
| knowledge_chunks | id, source_id, content, section_path, metadata, embedding, checksum |
| report_citations | id, report_id, recommendation_id, chunk_id, evidence_id, quote_span, relevance_score |
| workflow_runs | id, inspection_id, graph_version, status, checkpoint_ref, retry_count, error |
| workflow_events | id, run_id, sequence_no, type, payload, created_at |
| chats | id, owner_id, inspection_id, status, locale, created_at |
| resource_shares | id, resource_type, resource_id, subject_user_id, role, expires_at, revoked_at |

## 3. 索引

所有 owner 查询必须以 `owner_id` 开始；Inspection 按 `(owner_id, created_at)`，Evidence 按 `(inspection_id, room, created_at)`，Knowledge 按 `(kb_type, jurisdiction, effective_date)` 建索引。`workflow_events` 按 `(run_id, sequence_no)` 唯一；同一 Inspection 的 active run 建唯一约束；share 按 `(resource_type, resource_id, subject_user_id)` 唯一。pgvector 使用 HNSW，并结合全文检索做混合召回。

## 4. 迁移策略

1. 备份现有 MySQL；新建 PostgreSQL schema，只迁移现有业务表，不创建 Property/Repair。
2. 通过 backfill 从现有 reports/chat payload 生成 Inspection/Report/Evidence 映射；无法可靠映射的字段进入 `legacy_payload`，不得猜测生成 Evidence。
3. 双写新旧结构，比较结果。
4. 新 API 读取新结构，旧 API 读取 adapter。
5. 稳定后再删除旧列，过程可回滚。

P00 数据库切换必须先做离线导出、校验行数/checksum、外键检查、旧 API 回放和抽样报告对比；PostgreSQL 切换完成并观察稳定后，才能迁移工作流。不要在模型工作流迁移和数据库迁移同一发布中同时切换。
