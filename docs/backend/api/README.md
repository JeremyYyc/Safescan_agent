# 后端 API 契约规范

## 服务接口清单

- [Identity Access Service API](identity-access-api.md)

## 路径与版本

- 外部 HTTP 统一经 Nginx `/api`，服务 API 使用 `/api/v1/<resources>`。
- 健康检查不鉴权：`/health/live` 只检查进程，`/health/ready` 检查必要依赖。
- 资源使用复数名词和稳定 public ID；动作仅用于无法表达为资源状态变化的操作。
- 内部接口使用 `/internal/v1`，网关不得向公网暴露。

## 请求上下文

服务间统一传播：

- `Authorization: Bearer <token>`：用户或服务身份；
- `X-Request-ID`：入口请求 ID，不存在时由入口生成；
- `traceparent`：分布式追踪；
- `Idempotency-Key`：可重试写操作；
- `X-Actor-Subject`：仅由受信服务根据已验证 token 生成，禁止信任公网直传值。

## 成功与错误

成功响应直接返回资源或分页结果。错误采用稳定结构：

```json
{
  "error": {
    "code": "lease_state_conflict",
    "message": "租约当前状态不允许此操作",
    "request_id": "019...",
    "details": {}
  }
}
```

- `code` 是稳定机器键；`message` 可本地化；`details` 不包含密钥、SQL 或内部堆栈。
- 400 为协议错误，401 未认证，403 无权限，404 不可见/不存在，409 状态冲突，422 字段校验，
  429 限流，503 暂时不可用。
- Service 抛领域异常，统一异常处理器负责映射 HTTP；Mapper 异常不得原样返回。

## 分页、并发和幂等

- 大列表使用不透明 cursor，默认按 `(created_at, id)` 或业务排序键稳定排序。
- 可更新聚合返回 `version`/ETag，写入使用期望版本避免静默覆盖。
- 相同幂等键、主体和操作在有效期内必须返回同一业务结果；参数变化返回 409。
- 客户端只能重试明确标记可重试的超时、429 和 503，采用指数退避和抖动。

## 契约管理

- 每个 HTTP 服务导出 OpenAPI；每个事件有独立 JSON Schema/Pydantic schema 和版本。
- 生产者兼容旧消费者：新增字段默认可选，删除/改义必须升版本。
- Portal API 做消费者契约测试；领域服务做生产者验证。
- 日志记录 request ID、actor、service、operation、status 和 latency，不记录 token 或原始密码。
