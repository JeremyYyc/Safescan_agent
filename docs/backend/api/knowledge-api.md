# Knowledge Service API

> 状态：目标契约；P1，非本次全业务主链路阻塞项
> 所有者：`knowledge-service` / `knowledge` schema
> 容器监听端口：`8005`

## 1. 职责

本服务拥有知识库、文档版本、角色 ACL、索引和带来源检索。它不保存 Portal 页面状态，不保存
Agent 对话，也不执行房源、租约或维修动作。

## 2. API

| 方法与路径 | 请求 | 返回／权限 |
|---|---|---|
| `GET /health/live` | 无 | 进程存活 |
| `GET /health/ready` | 无 | DB、索引和对象存储状态 |
| `GET /internal/v1/knowledge-bases` | `audience? status? cursor?` | 按 public/tenant/staff ACL 过滤 |
| `POST /internal/v1/knowledge-bases` | `code,name,audience`；幂等键 | `201`；knowledge admin |
| `PATCH /internal/v1/knowledge-bases/{id}` | 字段、`version` | 更新；knowledge admin |
| `GET /internal/v1/knowledge-bases/{id}/documents` | `status? cursor?` | 有 ACL 的文档摘要 |
| `POST /internal/v1/knowledge-bases/{id}/documents` | file ID、document_key、metadata；幂等键 | `202 index_job_id` |
| `POST /internal/v1/documents/{id}/publish` | `version` | 原子切换 active version |
| `POST /internal/v1/search` | `query,base_ids?,limit,filters?` | 带 document/version/chunk/score 来源的结果 |
| `POST /internal/v1/retrieval` | `query,subject_context,limit` | 受信服务最小检索接口 |

## 3. 搜索响应

```json
{
  "data": [{
    "text": "...",
    "score": 0.86,
    "source": {
      "knowledge_base_id": "kb-uuid",
      "document_id": "doc-uuid",
      "document_key": "tenant-maintenance-guide",
      "version": 3,
      "chunk_id": "chunk-uuid"
    }
  }],
  "meta": {"query_id": "uuid"}
}
```

ACL 必须在检索前过滤；禁止先向量检索全部数据、返回前再删除无权结果。

## 4. 缓存与并发

- 公共已发布文档和查询结果可缓存 1–10min，key 包含 audience、ACL version、document version、
  normalized query/filter hash。
- Staff/tenant 结果不得共享 cache key；角色或文档发布事件主动失效。
- 热点查询使用 single-flight；空结果负缓存 ≤15s。
- 索引是持久异步 job，Redis Pub/Sub 只做通知；版本发布原子切换，失败索引不覆盖 active 版本。
- 批量 embedding 与数据库查询，限制 query 长度、limit 和每主体 RPS。

## 5. 错误与测试

错误结构和 HTTP 映射遵循 [统一错误契约](README.md)。本服务子码：
`knowledge_base_not_found`、`knowledge_access_denied`、`document_version_conflict`、
`index_job_failed`、`query_too_large`、`dependency_unavailable`、`dependency_timeout`、
`dependency_invalid_response`。

知识资源不存在或 ACL 不可见时统一返回 HTTP 404；内部可区分 `knowledge_base_not_found` 与
`knowledge_access_denied`，Portal 面向浏览器必须统一为 `resource_not_found`。

测试必须覆盖无 ACL 不泄漏、tenant/staff cache 隔离、重复入库幂等、版本回滚、索引失败保留
旧 active 版本，以及 Redis 故障时安全回源。
