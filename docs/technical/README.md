# SafeScan 技术文档体系

本文档目录将冻结后的 PRD 转化为工程实施资料。当前文档为 v1.0 技术基线，技术实现以当前仓库为基线，新增能力通过兼容层和灰度开关逐步落地。PRD 冻结后，需求变更必须通过变更记录更新版本，不直接静默修改冻结内容。

## 文档清单与计划

| 顺序 | 文档 | 目的 | 阶段 |
|---:|---|---|---|
| 1 | [技术架构总览](./01-architecture.md) | 系统边界、组件和数据流 | P0 |
| 2 | [前端技术文档](./02-frontend.md) | 页面、状态、组件、SSE 和错误体验 | P0 |
| 3 | [后端技术文档](./03-backend.md) | 分层、服务、任务、异常和配置 | P0 |
| 4 | [接口文档](./04-api.md) | REST/SSE 资源、请求响应和兼容策略 | P0 |
| 5 | [数据模型与迁移](./05-data-model.md) | 核心实体、索引、权限与迁移 | P0/P1 |
| 6 | [AI、Evidence 与 RAG](./06-ai-rag.md) | 感知、知识库、混合检索和引用 | P0 |
| 7 | [LangGraph 工作流](./07-workflow.md) | State、节点、重试、人工确认 | P0/P1 |
| 8 | [部署与运维](./08-deployment.md) | 本地、Docker、环境、观测和成本 | P0 |
| 9 | [安全与隐私](./09-security.md) | 认证、授权、上传、数据和审计 | P0 |
| 10 | [测试与 AI 评测](./10-testing-evaluation.md) | 单测、集成、离线评测和发布门槛 | P0 |
| 11 | [迁移与发布 Runbook](./11-migration-runbook.md) | PostgreSQL P00、AutoGen、API 和回退 | P00/P0/P1 |
| 12 | [中国大陆 Safety KB 调研](./12-safety-kb-research-cn.md) | 首批六类知识资源与审核规则 | P0 |
| 13 | [CI/CD 技术文档](./13-cicd.md) | CI 门禁、触发器、Docker 和发布边界 | P00 |
| 14 | [Qwen 统一模型栈](./14-qwen-model-stack.md) | Qwen 文本、视觉、Embedding、Rerank、路由和发布治理 | P0/P1 |
| 15 | [Docker 统一环境配置](./15-environment-configuration.md) | Compose env 文件、服务注入、密钥和环境迁移 | P00/P0 |

## 编写顺序

1. P00-A：基于当前 MySQL 建立并强制执行 CI/CD 基线。
2. P00-B：完成 MySQL → PostgreSQL 迁移、数据校验和回退演练。
3. P00-C：将 PostgreSQL 集成测试加入 Required Checks，并移除 MySQL 事实源依赖。
4. 冻结中国大陆/简体中文产品边界、实体和接口契约。
5. 实现 Evidence/schema 与工作流兼容层。
6. 实现 Product/Safety KB 和引用式报告。
7. 后续再实施 Property、Regulation、Device、长期 Memory 和 Rental 能力。

## 统一约定

- API 前缀为 `/api/v1`；现有旧路径保留兼容期。
- 所有 Inspection、Report、Chat、Media 查询必须经过 owner/share 授权；不能只依赖前端隐藏按钮。
- ID 使用 UUID；时间统一 ISO 8601 UTC。
- 错误格式统一为 `{"error": {"code", "message", "details", "request_id"}}`。
- 除明确列出的临时错误外，客户端不得自动重试；异步任务必须有终态和重试上限。
- SSE 只是通知通道，REST 状态和事件回放才是恢复依据。
- 不把用户视频、模型原始响应或密钥写入普通日志。
- 所有模型输出先过 schema validation，再进入下游节点。
- CI 采用渐进式演进；新增模块必须同步增加测试并登记到 [CI/CD 技术文档](./13-cicd.md) 的能力表。
