# 前端技术文档

## 1. 当前基线

前端使用 React 19、Vite、React Router。MVP 默认 `locale=zh-CN`，所有用户可见文案和模型回复展示简体中文；文案通过 locale 资源文件管理，预留 `en-US`，不在 MVP 强制实现切换。

## 2. 页面与路由

```text
/login
/dashboard
/inspections/new
/inspections/:id/progress
/inspections/:id/evidence
/inspections/:id/report
/inspections/:id/chat
/properties/:id/timeline
/settings/profile
```

MVP 先实现 `new → upload → progress → report → chat`；Property timeline 和可暂停人工确认随后启用。MVP 的低置信度结果只提供确认/忽略标记，不阻塞报告完成。

## 3. 前端状态

按作用域分为：

- Auth：token、用户、过期和登出。
- Inspection：任务、媒体、状态、错误和当前报告。
- Evidence：按房间/风险过滤的证据列表和当前帧。
- Chat：消息、引用、流式状态和报告上下文。
- UI：toast、modal、确认弹窗和加载状态。

建议使用现有 React 状态方案先建立 domain hooks，避免组件直接调用 fetch：`useInspection`、`useWorkflowEvents`、`useReport`、`useKnowledgeChat`。

## 4. 组件契约

核心组件：`InspectionCreateForm`、`UploadDropzone`、`ProcessingTimeline`、`EvidenceViewer`、`HazardCard`、`CitationList`、`ReportSummary`、`HumanConfirmationDialog`、`ChatPanel`。

组件只接收已验证的 DTO；后端错误统一转为用户可理解的提示，同时保留 request_id 供支持排查。

## 5. 处理进度与 SSE

前端订阅 `/api/v1/inspections/{id}/events`，事件类型：`workflow_started`、`stage_started`、`stage_completed`、`evidence_created`、`approval_required`、`workflow_failed`、`workflow_cancelled`、`workflow_completed`。服务端只推送已持久化事件，并支持 `Last-Event-ID` 回放；断线或事件缺口时从 `GET /status` 和事件回放接口补齐。

## 6. UX 要求

- 显示“处理中/等待确认/已完成/失败可重试”，不显示无意义的模型内部术语。
- 风险卡片必须显示严重程度、置信度、证据入口和来源入口。
- 不确定结论使用明确文案，不使用确定性的红色警报样式。
- 视频和图片加载失败时展示占位与重试。
- 上传中刷新页面不能丢失 `inspection_id` 和已完成的 `media_asset_id`；重复点击启动不能创建多个 run。
- 取消、重试、删除和确认等有副作用的操作必须二次确认，并显示最终服务端状态。
- 桌面端优先，关键操作支持键盘和可读的颜色对比。

## 7. 错误与缓存

API client 统一处理 401、403、404、409、422、429、5xx。报告详情可缓存，工作流状态和聊天消息使用重新验证；上传过程不可因页面刷新丢失任务 ID。
