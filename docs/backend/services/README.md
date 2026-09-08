# 后端服务目录

本目录按数据所有权维护服务设计。每份服务文档至少说明职责、拥有的数据、分层模块、外部
依赖和首批测试；接口字段的唯一事实来源将在实现阶段由 OpenAPI 与事件 schema 生成。

| 服务文档 | 数据 schema | 进程类型 |
|---|---|---|
| [身份与权限](identity-access-service.md) | `identity_access` | HTTP API |
| [房源与租赁](property-leasing-service.md) | `property_leasing` | HTTP API + event consumer |
| [维修](maintenance-service.md) | `maintenance` | HTTP API + event consumer |
| [检查与报告](inspection-report-service.md) | `inspection_report` | HTTP API + worker |
| [知识库](knowledge-service.md) | `knowledge` | HTTP API + indexing worker |
| [员工 Agent](staff-agent-service.md) | `staff_agent` | streaming HTTP API + worker |
| [Portal API](portal-apis.md) | 无 | HTTP BFF |

所有服务统一采用 [Controller / Service / Mapper / Model](../architecture/layering.md) 分层。
