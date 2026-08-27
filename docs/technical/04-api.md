# API 接口文档（初稿）

Base URL：`/api/v1`。除登录注册外均需 `Authorization: Bearer <token>`。所有资源接口执行 owner/share 授权；不存在或无权访问的资源统一返回 404，避免泄露资源存在性。

## 1. 通用响应与错误

```json
{"data": {}, "request_id": "req_01"}
```

```json
{"error":{"code":"FORBIDDEN_RESOURCE","message":"无权访问该资源","details":{}},"request_id":"req_01"}
```

## 2. Inspection

### `POST /inspections`

请求：`{"mode":"safety","locale":"zh-CN","region":{"country":"CN","province":"广东省","city":"深圳市"},"title":"厨房检查"}`。MVP 只接受 `mode=safety`；地区字段用于上下文，不用于生成法规结论，P00 不建立 Property 关系。

响应：`{"data":{"id":"uuid","status":"created","mode":"safety"},"request_id":"..."}`

### `POST /inspections/{id}/media`

`multipart/form-data`，字段 `file`、可选 `room`。校验 MIME、扩展名、大小和病毒扫描状态。响应返回 `media_asset_id`，不代表已完成分析。

### `POST /inspections/{id}/run`

请求头要求 `Idempotency-Key`。响应：`{"data":{"workflow_run_id":"uuid","status":"queued"}}`。

### `GET /inspections/{id}`

返回任务基本信息、状态、模式、地区和时间。

### `GET /inspections/{id}/status`

返回当前阶段、百分比（若可计算）、错误、是否需要确认和最后更新时间。

### `POST /inspections/{id}/cancel`

仅允许 `queued`、`running`、`waiting_confirmation`。取消是幂等操作，返回 `cancelled` 或当前终态。

### `POST /inspections/{id}/retry`

仅允许从 `failed` 或 `cancelled` 重试；创建新 `workflow_run_id`，不覆盖旧 run。请求头使用 `Idempotency-Key`。

### `DELETE /inspections/{id}`

执行可恢复软删除，写入 `deleted_at` 和 `deleted_by`，并停止未完成 run。默认恢复窗口为 30 天；软删除资源默认不出现在列表和普通查询中。

### `POST /inspections/{id}/restore`

仅允许资源所有者在恢复窗口内调用；恢复 Inspection 及其关联 Report、Evidence、Chat 元数据，但不恢复已被用户明确删除的单个媒体。

### `POST /exports`

创建异步 ZIP 数据导出任务。请求指定 `inspection_ids` 或 `scope=all`；服务端再次执行权限校验。响应返回 `export_job_id`。

### `GET /exports/{id}`

返回导出状态：`queued`、`running`、`completed`、`failed`、`expired`。完成后返回限时下载 URL；导出包结构为 `manifest.json`、`inspections/*.json`、`evidence/*.json`、`reports/*.json`、`reports/*.pdf`、`media/metadata.json`，不包含 API Key、内部 Prompt 或其他用户数据。

### `GET /inspections/{id}/events`

SSE（`Accept: text/event-stream`）。事件统一包含 `id`、`type`、`inspection_id`、`run_id`、`sequence_no`、`timestamp`、`data`。事件先写入 `workflow_events` 再推送；支持 `Last-Event-ID`。

### `GET /inspections/{id}/events/history?after=<event_id>`

返回已持久化事件列表，用于 SSE 断线后的补齐；不是实时流。

## 3. Evidence、Report 与确认

### `GET /inspections/{id}/evidence`

参数：`room`、`source_type`、`min_confidence`、`page`、`page_size`。返回证据及受控媒体 URL。

### `GET /inspections/{id}/report`

返回版本化结构化报告：`summary`、`rooms`、`hazards`、`recommendations`、`citations`、`model_info`、`disclaimer`。

### `POST /inspections/{id}/confirmations`

请求：`{"evidence_id":"uuid","decision":"confirmed|rejected|edited","note":"...","attributes":{}}`。MVP 只记录标记；P1 若任务处于 waiting_confirmation 才允许恢复 workflow。只追加审计记录，不修改原始模型输出。

### `POST /inspections/{id}/export-pdf`

异步生成或返回最新已发布 PDF 资源；仅允许资源拥有者或有下载权限的共享者访问。报告未完成时返回 `REPORT_NOT_READY`。

## 4. Knowledge 与 Chat

### `POST /knowledge/search`

请求：`{"query":"为什么这个风险危险？","kb_types":["safety"],"jurisdiction":{"country":"CN","province":"广东省","city":"深圳市"},"top_k":5,"inspection_id":"uuid"}`。响应返回 `chunk_id`、标题、片段、score、trust_tier、来源 URL 和适用范围。MVP 不接受 regulation 作为可生成合规结论的 KB 类型。

### `POST /chats/{chat_id}/messages`

请求：`{"content":"这个风险为什么存在？","inspection_id":"uuid","stream":true}`。服务端必须验证 chat 对用户和 inspection 的绑定；响应或 SSE 返回消息、引用、拒答原因和 request_id。没有足够上下文时必须返回 `KNOWLEDGE_UNAVAILABLE` 语义，而不是编造。

## 5. 兼容接口

现有 `/uploadVideo`、`/processVideoStream`、报告和聊天接口在迁移期继续工作，由 adapter 映射到新 Inspection Service；新功能只使用 `/api/v1`。
