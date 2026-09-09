# Inspection Report Service API

> 状态：目标契约 + 旧业务兼容契约
> 所有者：`inspection-report-service` / `inspection_report` schema
> Worker：`inspection-report-worker`，与 API 属于同一服务边界
> 容器监听端口：`8004`

## 1. 迁移原则

本服务拥有检查、property report、文件、视频分析 job、证据、PDF 和报告访问规则。每份报告
必须直接关联一个 property；旧 chat/workspace 仅作为迁移 adapter 的私有上下文，不再是业务
父实体。新 API 只为现有 Pipeline 增加标准入口、property 关系、subject 授权和稳定 public ID；以下
旧业务保持原样：

- 视频流式上传和 MinIO 私有对象语义；
- 抽帧、筛选、YOLO、视觉模型、报告写作、评分、验证和修复；
- `WorkflowOrchestrator().execute_workflow(...)` 调用链；
- report JSON、regionInfo、representativeImages 与 PDF 内容语义；
- PostgreSQL 持久 job、worker claim、lease/heartbeat、retry 和恢复规则。

禁止为了拆服务复制第二套 Pipeline 或让新旧路径同时写同一 job/report。

## 2. 数据补充

核心关系和迁移字段：

```text
reports
- public_id
- property_id UUID                 必填，业务父实体
- source_lease_id UUID?            tenant 生成时记录授权来源
- created_by_subject_id UUID
- created_by_account_type
- legacy_context_id bigint/uuid?   仅 adapter 私有，不对外返回
- title/status/pipeline_version/completed_at/version
```

Report 状态为 `draft → processing → active|failed`，以及管理删除后的 `deleted`。旧 Pipeline 只决定
分析结果；新 adapter 负责在同一 report 上推进这些外围持久状态。

P0 不建立独立报告 ACL/Grant 表。`property_id` 是报告业务归属，`source_lease_id` 是租客可见性的
唯一租期来源：Tenant 生成时绑定当前唯一 active Lease；员工为存在 active Lease 的在租房源生成时
自动绑定该 Lease；员工为空置房源生成时为 null，仅 staff scope 可见。仅住过同一 property 不代表
能看到该房产所有报告，未来租客不得继承旧租期报告。

Customer 读取分两类：当前 Tenant 必须满足 `report.source_lease_id = 本人唯一 active lease.id` 且
property 匹配；Former Tenant 必须从本人 `ended/terminated` 历史 Lease 的房源入口读取相同
`source_lease_id` 的报告。executed 待入住 Tenant 不能读取报告。Staff 读取继续使用 permission +
property scope，不受 Customer 状态规则替代。
`property_id`、`source_lease_id`、`created_by_subject_id` 创建后不可修改；如果绑定错误，命令整体
失败并重建正确 report，不允许 PATCH 把报告移动到另一房产或租期。

## 3. 公共结构

### 3.1 JobView

```json
{
  "id": "job-uuid",
  "type": "video_analysis",
  "status": "running",
  "stage": "scene_understanding",
  "progress_percent": 58,
  "attempt": 1,
  "max_attempts": 3,
  "report_id": "report-uuid",
  "error": null,
  "created_at": "2026-09-08T10:00:00Z",
  "updated_at": "2026-09-08T10:02:00Z"
}
```

新 Portal 路径先创建 draft report，再创建 job，因此 `video_analysis/pdf_render` 的 `report_id` 必填。
仅旧兼容路径的迁移响应可以暂时为 null，且不得进入新 `JobView` schema。

### 3.2 ReportSummary

```json
{
  "id": "report-uuid",
  "property_id": "property-uuid",
  "source_lease_id": "lease-uuid",
  "property": {"id": "property-uuid", "address": "Sydney NSW"},
  "title": "Home Safety Inspection",
  "source": "video_analysis",
  "status": "active",
  "completed_at": "2026-09-08T10:10:00Z",
  "validation_passed": true,
  "can_download": false
}
```

Staff detail可返回完整结构化 report payload；tenant detail 应按产品策略裁剪内部 validation、
模型诊断和对象元数据。

## 4. 新内部 API

### 4.1 健康检查

| 方法 | 路径 | 返回 |
|---|---|---|
| GET | `/health/live` | API 进程存活 |
| GET | `/health/ready` | DB/migration、MinIO 和关键配置就绪 |
| GET | `/internal/v1/workers/health` | queue depth、oldest queued、stale lease；仅平台 |

### 4.2 Property Report

| 方法与路径 | 请求 | 返回／权限 |
|---|---|---|
| `POST /internal/v1/properties/{property_id}/reports` | `title?`；幂等键 | `201 ReportView(status=draft)`；source_lease_id 由服务端推导；tenant 当前租约或有权 staff |
| `GET /internal/v1/properties/{property_id}/reports` | `mine? source_lease_id? cursor?` | Customer 按本人 source Lease，staff 按 property scope 返回 |
| `GET /internal/v1/reports/{report_id}` | `projection=staff|tenant` | 直接包含 property_id 的 ReportView |
| `PATCH /internal/v1/reports/{report_id}` | `title?,version` | P1；有权 staff；Tenant 不提供报告修改接口 |

创建权限固定为：Tenant 必须具有 `report:self:create` 且 Leasing 确认其唯一当前租约状态为 active
并指向该 property；executed 待入住阶段不得创建。Property Manager 必须具有
`report:generate_assigned` 并命中 building/property scope；
Manager Admin 使用 `report:generate_all`。Leasing Consultant 和 Maintainer 不得创建报告。
Tenant 创建时 source_lease_id 由当前唯一 active Lease 推导；staff 创建时服务端自动查询该 property
的 active Lease 并绑定，若不存在则保存 null。浏览器不得自行选择其他租客或 source lease。

### 4.3 文件上传

| 方法与路径 | 请求 | 返回／权限 |
|---|---|---|
| `POST /internal/v1/reports/{report_id}/files/videos` | raw `video/*` body；`X-File-Name`、`X-Content-SHA256?`、幂等键 | `201 FileView`；报告创建者或有权 staff |
| `POST /internal/v1/files/pdfs` | raw `application/pdf` body | legacy compatibility/P1；`201 FileView`；有权 staff |
| `GET /internal/v1/files/{file_id}/content` | 可选 Range | 受控流式内容；严格 creator、本人 source Lease 或 staff scope |
| `DELETE /internal/v1/files/{file_id}` | `version` | 无活跃引用时软删除/排队清理 |

Portal 和 API 必须流式转发并设置一致的 body limit；文件先写 `uploading`，校验完成后变 `ready`。
失败对象标记 orphaned 并由独立清理任务处理。任何响应不返回 bucket/object_key。

### 4.4 视频分析任务

| 方法与路径 | 请求 | 返回／权限 |
|---|---|---|
| `POST /internal/v1/reports/{report_id}/jobs` | `input_file_id,attributes{}`；幂等键 | `202 JobView`；重新校验 report→property 权限 |
| `GET /internal/v1/report-jobs/{job_id}` | 无 | JobView + steps/events 摘要 |
| `GET /internal/v1/report-jobs/{job_id}/events` | `after_sequence?`，SSE 或 NDJSON | 可恢复增量事件流 |
| `POST /internal/v1/report-jobs/{job_id}/cancel` | `reason`；幂等键 | `202 cancel_requested`；非终态 |

同一 report 同时最多一个 queued/retry_wait/running job；同一 actor+幂等键返回原 job。提交成功后立即返回，客户端断开不
取消任务。worker 使用 `FOR UPDATE SKIP LOCKED` 原子领取、短事务提交、周期 heartbeat；lease
过期后可重领，完成前检查 report 唯一约束。

### 4.5 报告和 PDF

| 方法与路径 | 请求 | 返回／权限 |
|---|---|---|
| `GET /internal/v1/reports` | `property_id? source_lease_id? mine? cursor?` | Customer 按本人 source Lease，staff 按 property scope |
| `POST /internal/v1/reports/{report_id}/exports/pdf` | 幂等键 | P1；`202 pdf_render JobView` 或已有 PDF |
| `GET /internal/v1/reports/{report_id}/exports/latest` | 无 | P1；PDF metadata；不返回对象 key |
| `GET /internal/v1/reports/{report_id}/download` | 无 | P1；`application/pdf`；仅有权 staff scope |
| `DELETE /internal/v1/reports/{report_id}` | `version,reason` | P1；软删除；报告管理 staff |

### 4.6 P0 报告访问规则

- Tenant 创建报告时，Report Service 向 Leasing 查询唯一 active Lease 并服务端写入
  `source_lease_id/property_id`；请求不得提交或覆盖 subject/lease/property。
- Property Manager/Manager Admin 创建报告时，服务端查询 property 的唯一 active Lease；存在则
  使用 Property Leasing `property-access:check` 返回的 `active_lease_id` 自动绑定
  `source_lease_id`，不存在则为 null 且仅 staff scope 可见。
- Tenant 只能查看 source_lease_id 等于本人 active Lease 的报告；Former Tenant 只能从本人历史
  Lease 房源入口查看同一 source_lease_id 报告，并且只读、不可下载。
- Staff 使用 permission + property scope 查看和生成；导出、下载为 P1。P0 不提供共享、ACL、owner
  转移或客户报告管理接口。
- Identity 的 customer_status 只决定能力上限，不能替代 Leasing 的承租关系、Lease 状态和
  property 匹配检查。Prospect、公开访问者和未来租客不能列举或读取报告。
- 当前报告列表只需向 Leasing 查询一次当前 Lease；历史路由只验证一次 URL 中的 lease_id，然后
  在本库按 `source_lease_id` 过滤，禁止逐条报告跨服务查询形成 N+1。

### 4.7 Subject 删除

| 方法与路径 | 请求 | 返回／权限 |
|---|---|---|
| `POST /internal/v1/privacy/subject-deletions/{request_id}` | `subject_id,requested_at`；事件重放幂等 | `202 accepted|duplicate`；仅 Identity deletion worker |
| `GET /internal/v1/privacy/subject-deletions/{request_id}` | 无 | 删除/对象清理进度；仅 Identity deletion worker |

处理器删除该 tenant 创建的 report 及 files/MinIO objects。员工生成、仍属于 property 的 report
保留；其中不得复制租客 PII，Property Leasing 删除 lease/subject 映射后，残留 source_lease_id
不能再解析为客户访问关系。对象删除失败保持 pending 并重试，不得提前回执 completed。

## 5. 旧外部兼容 API

以下是当前 `backend/app` 的真实运行契约，迁移期间保留：

| 方法与路径 | 当前行为 | 新契约映射 |
|---|---|---|
| `POST /api/uploadVideo` | raw video，返回 `video_asset_id` | 新路径先建 draft report，再调用 `POST /internal/v1/reports/{report_id}/files/videos` |
| `POST /api/processVideoStream` | `video_asset_id,attributes,chat_id`；NDJSON 进度 | Adapter 以 report 的私有 legacy_context_id 填充 chat_id |
| `GET /api/report-jobs/{job_id}` | 返回 job、steps、events | 新 job 查询 |
| `POST /api/reports/{chat_id}/export-pdf` | 同步调用旧 PDF graph | 新 PDF job/查询 |
| `GET /api/reports/{chat_id}/pdf-latest` | 最新 PDF 元数据 | report latest export |
| `GET /api/reports/pdf/{report_id}/download` | 旧 owner 校验后下载 | 新 Portal 仅 staff scope 下载 |
| `POST /api/reports/upload-pdf` | raw PDF | 新 files/pdfs + report metadata |
| `POST/GET /api/chats...` | 旧 report workspace 时间线 | 仅迁移兼容；新业务不暴露 chat/workspace |

兼容路径继续使用旧 owner 校验；切至 Portal 后使用 subject、property、`source_lease_id` 和 Lease 关系。
迁移每一步都必须保证只有一个 writer。

新路径先创建 draft report，job 持有该 report_id。旧 Workflow 的分析/校验步骤保持不变；唯一允许
调整的是 persistence adapter：完成时把原 report JSON、analysis 和 assets 写入该 draft 并转为
active，不再 INSERT 第二份 report。旧兼容路径在切换前仍由原 writer 创建 report；同一请求绝不
同时经过新旧 writer。

## 6. 事件流格式

SSE 推荐事件：`job.created`、`job.started`、`step.progress`、`job.retry_wait`、`job.completed`、
`job.failed`、`job.cancelled`。每条包含递增 `sequence_no`、job ID、stage、progress 和安全 message。

```json
{
  "sequence_no": 12,
  "type": "step.progress",
  "job_id": "job-uuid",
  "stage": "hazard_analysis",
  "progress_percent": 70,
  "message": "Hazard analysis complete",
  "occurred_at": "2026-09-08T10:05:00Z"
}
```

不得向浏览器发送模型隐藏推理、原始 provider 错误、凭据、对象 key 或内部堆栈。

## 7. 错误码

错误结构和 HTTP 映射遵循 [统一错误契约](README.md)。本服务子码：
`inspection_not_found`、`property_access_denied`、`report_generation_not_allowed`、
`current_lease_required`、通用 `unsupported_media_type`、`payload_too_large`、
`file_not_ready`、`file_quarantined`、`active_job_exists`、`job_not_found`、
`report_generation_failed`、`report_validation_failed`、`report_not_found`、
`report_access_denied`、`report_history_access_required`、`lease_report_mismatch`、`version_conflict`、
`idempotency_conflict`、`dependency_unavailable`、`dependency_timeout`、
`dependency_invalid_response`。

模型失败不得返回伪造成功报告；失败类别持久化到 job event，公共 message 本地化且脱敏。
报告、job、inspection 不存在或对 actor 不可见时统一返回 HTTP 404；本服务内部可保留对应诊断
子码，Portal 面向浏览器必须统一为 `resource_not_found` 和空 details。

## 8. 缓存与高并发

- 不缓存上传 body、运行中 Pipeline state 或授权决定的无版本副本。
- 报告摘要可缓存 30–60s；key 包含 projection、subject、lease/relationship version、report version。
- 完整报告 JSON 可缓存 1–5min，但 staff/tenant 使用不同 key；Lease/report 变化主动失效。
- Redis Pub/Sub 可降低多实例 SSE 轮询延迟，但 PostgreSQL `report_job_events` 是恢复真相。
- 下载可使用短期单次/受控 URL，TTL ≤60s，并绑定 subject/action；Portal 不缓存 URL。
- 上传限流按 subject + IP，worker 并发按 CPU/GPU、模型配额和内存独立配置。
- 旧代码的进程内 upload slot 继续保留；多 API 实例前增加 Redis/Gateway 分布式 admission
  control，作为外围容量保护，不修改上传与 Pipeline 内核。
- 多 worker 依赖数据库 claim/lease；Redis 故障不能导致 job 丢失或重复完成。
- MinIO、HTTP 和 DB 客户端使用连接池；大文件全过程 backpressure，不 `await body()` 全量读内存。

## 9. 事件

| 事件 | 关键 payload |
|---|---|
| `report.created.v1` | `report_id,property_id,source_lease_id?,created_by_subject_id` |
| `report.completed.v1` | `report_id,property_id,validation_passed,completed_at` |
| `report.failed.v1` | `job_id,report_id,property_id,error_code,attempt` |
| `report.deleted.v1` | `report_id,property_id,deleted_at` |

## 10. 回归与契约测试

1. 固定视频 + mock provider 下，新旧路径关键报告字段和证据顺序一致。
2. API/SSE/worker 重启不丢任务；过期 lease 可重领且只生成一个 report。
3. 非视频、超大小、跨用户 file ID、report/property 不一致均拒绝。
4. Tenant 与 report.source_lease_id 不匹配、Lease 尚未 active 或非本人承租关系时读取返回内部 404，
   Portal 对浏览器统一为 `resource_not_found`。
5. source_lease_id 与 property 不匹配时拒绝创建且不写 report/job。
6. Redis/PubSub 故障不影响 job 持久恢复。
7. 兼容 API 在 Portal 完成切换前通过原前端回归；之后才移除 Gateway 路由。
8. Tenant 只能为唯一当前租约 property 生成；Property Manager 只能按 scope 生成；其他员工拒绝。
9. 新 ReportView/API 不返回 chat_id/legacy_context_id，且每个 report 都有 property_id。
10. 新路径完成时只更新预创建 draft report，不额外 INSERT 第二份 report；旧路径输出回归不变。
11. lease ended/terminated 后 Former Tenant 只能从历史 Lease 入口只读；subject deletion 重放不会误删员工生成的 property report。
12. Customer 侧只有当前 Tenant 可创建报告；Former Tenant 只能经历史 lease/property 关系读取，
    Prospect、公开访问者和未来租客均不能发现报告。
13. executed 待入住 Tenant 只能查看合同和待入住房产，不能创建报告；starts_on 激活后才开放。
14. PATCH 或内部事件均不能修改既有 report 的 property_id/source_lease_id/creator。
