# knowledge-service

## 职责

负责知识库、角色访问控制、文档版本和可追溯检索。它返回带来源的知识片段，不保存员工
Agent 的对话，也不直接决定业务动作。

## 数据所有权

`knowledge_bases`、`knowledge_role_access`、`knowledge_documents`，以及本 schema 的
outbox/inbox 表。向量 chunk、embedding job 等扩展表也必须留在该 schema。

## 模块建议

- Controllers：bases、documents、search、internal-retrieval。
- Services：文档入库、版本激活、ACL、混合检索、来源投影。
- Mappers：KnowledgeBase、KnowledgeDocument、RoleAccess、Chunk/IndexJob。
- Workers：解析、切片、embedding、索引切换和清理。

## 关键约束与测试

- ACL 使用稳定角色/主体上下文，检索前过滤，不在返回后补过滤。
- 文档版本切换原子化；索引失败不覆盖当前 active 版本。
- 每条检索结果包含 document/version/chunk 来源和分数。
- 测试覆盖无权限不泄漏、重复入库幂等、版本回滚和索引失败恢复。
