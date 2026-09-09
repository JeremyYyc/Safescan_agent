# inspection-report-service

## 职责

负责检查工作区、上传文件、视频分析任务、检查发现、结构化报告、PDF 和对象存储元数据。
`inspection-report-worker` 是同一服务的异步进程，不是新的数据所有者。

## 数据所有权

`report_workspaces`、`report_workspace_messages`、`files`、`reports`、`report_analysis`、
`report_pdf`、`report_assets`、`inspections`、`inspection_findings`、`inspection_reports`、
`report_jobs`、`report_job_steps`、`report_job_events`、`report_workspace_items`，以及本 schema
的 outbox/inbox 表。

## 模块建议

- Controllers：uploads、workspaces、jobs、reports、assets、exports。
- Services：上传编排、报告任务、检查聚合和报告查询；PDF 导出保留为旧业务兼容能力，在新 Portal 中属于 P1。
- Mappers：Workspace、File、Report、Inspection、ReportJob。
- Workers：视频抽帧/视觉分析、报告生成、PDF、对象清理。
- Domain：任务状态机、报告版本、对象 key 规则和模型失败分类。

## 关键约束与测试

- 文件内容只进入私有 MinIO，数据库保存对象 key、摘要、大小和媒体类型。
- Worker 通过租约领取持久任务；重试、取消和完成必须满足版本条件。
- 外部模型失败不可伪造成成功报告；失败类别写入 job event。
- P0 测试覆盖无模型的上传/任务状态、对象访问控制、恢复和重复消费；旧 PDF 导出继续做兼容回归，但不阻塞新 Portal P0。
