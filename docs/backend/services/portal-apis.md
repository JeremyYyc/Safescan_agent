# staff-portal-api 与 tenant-portal-api

## 定位

Portal API 是面向具体前端体验的 BFF。它们聚合领域服务、裁剪字段并提供稳定页面契约，
不拥有业务表，不复制领域状态机，也不绕过领域服务授权。

## staff-portal-api

- 面向员工正常页面；根据角色和资源范围聚合房源、租约、维修、检查和报告。
- 与 `staff-agent-service` 并行，普通页面操作不经过 Agent。
- 可以做短期只读缓存，不缓存授权决定和高风险写入结果。

## tenant-portal-api

- 面向匿名潜客、注册客户、租客和历史租客。
- 公开列表、个人租约、维修请求和报告访问使用不同投影。
- guest subject 升级为 user subject 时只调用身份服务的受控认领流程。

## 分层建议

Portal 仍使用 Controller/Service/Client/Schema；因为无自有业务表，通常不需要 Mapper/Model。
若需要保存 UI 偏好，应先判断它是否属于身份服务，不能为了满足目录模板而创建数据库。

## 测试

- OpenAPI/消费者契约测试固定页面所需字段。
- 使用领域服务 stub 测试聚合、部分失败、超时和错误转换。
- 端到端测试验证网关路径、subject 传播、资源级 403 和字段脱敏。
