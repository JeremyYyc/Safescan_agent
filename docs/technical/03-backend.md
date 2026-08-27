# 后端技术文档

## 1. 分层结构

```text
api/                 Controller、DTO、鉴权依赖
services/            业务用例与事务边界
repositories/        数据访问与查询
domain/              Pydantic/领域模型、枚举、错误
workflow/             LangGraph 图、节点、checkpoint
ai/                  Provider、Perception、Retrieval
storage/             对象存储和路径隔离
observability/       日志、trace、metrics
```

当前 `backend/app/api`、`agents`、`workflow` 逐步映射到上述边界，不要求一次性移动文件。

## 2. 请求处理链

```text
Middleware(request_id/auth/rate-limit)
 → Controller(validate DTO)
 → Service(authorization + transaction)
 → Repository/Provider
 → Response DTO
```

Controller 不直接调用 LLM，不拼接复杂 SQL，不通过异常字符串判断业务状态。

## 3. 任务模型

Inspection 处理必须异步。创建任务后返回 `inspection_id`；媒体校验完成后启动 run，返回 `workflow_run_id`。worker 执行视觉和 Agent 节点，状态写入数据库，前端通过 SSE 接收通知并用 REST 确认状态。

状态：`created`、`uploaded`、`queued`、`running`、`waiting_confirmation`、`completed`、`failed`、`cancelled`。

MVP 媒体策略：单个视频最长 30 分钟、最大 2 GB。服务端必须用媒体探测结果校验时长，不能只相信文件名或客户端参数。当前项目约按 1 FPS 抽取原始帧，30 分钟可能产生约 1800 帧；因此应在抽取阶段增加硬上限/分段策略，再由现有代表性图片选择逻辑保留最多 15 张代表图。15 张是代表图上限，不是原始抽帧上限。

删除采用软删除优先：API 写入 `deleted_at`，查询默认过滤；后台清理任务在 30 天恢复窗口后物理删除媒体和派生索引。导出任务必须按 owner/share 权限生成，不能通过导出绕过资源授权。

重复请求通过 `Idempotency-Key` 防止重复创建资源；同一 Inspection 同时只允许一个 active run。重试创建新 run，不覆盖旧 run；取消只允许 queued/running/waiting_confirmation。

## 4. 错误处理

业务错误使用固定 code，如 `INSPECTION_NOT_FOUND`、`FORBIDDEN_RESOURCE`、`INVALID_MEDIA`、`WORKFLOW_BUSY`、`MODEL_TIMEOUT`、`SCHEMA_VALIDATION_FAILED`、`KNOWLEDGE_UNAVAILABLE`。内部异常记录完整 trace，外部只返回安全信息和 request_id。

## 5. 事务与一致性

数据库事务只负责元数据；对象存储和模型调用通过状态机协调。对象上传成功但数据库失败时由清理任务回收孤儿对象；记录存在但对象不可用时进入 `media_unavailable`。报告采用 draft → validate → published，禁止前端读取半成品。

## 6. LLM Provider

```python
class LLMProvider:
    async def generate(self, messages, *, model_tier): ...
    async def generate_structured(self, messages, schema, *, model_tier): ...
    async def vision(self, image, prompt, *, model_tier): ...
    async def embed(self, texts): ...
```

DashScope 是首个实现；业务 Agent 不得依赖 DashScope SDK 的具体返回结构。

## 7. 数据访问与性能

使用 Repository + Service；列表接口统一分页、字段选择和排序。避免循环查询 Evidence、Citation 和房间信息；使用批量查询。连接池、模型并发和上传大小均配置化。

## 8. 后台任务可靠性

节点必须幂等，输入输出带 schema/version；失败记录 retry_count、last_error 和可恢复 checkpoint。模型调用使用指数退避和总超时，非瞬时错误进入 failed，不无限重试。
