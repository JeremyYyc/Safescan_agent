# 后端本地开发与运行

## 前置条件

- Docker Engine / Docker Desktop，支持 `docker compose`。
- 仅做宿主机测试时使用 Python 3.11+。
- 从根 `.env.example` 复制唯一的根 `.env`，填入随机鉴权密钥、数据库/MinIO 密码和模型密钥。

## Docker 启动

```sh
docker compose config
docker compose up --build
```

默认入口为 `http://127.0.0.1:8080`：

- 应用存活：`GET /health`
- 鉴权/数据库就绪：`GET /health/auth`
- Identity 外部 API：`/api/v1/auth/*`、`/api/v1/me*`、`/api/v1/iam/*`
- Identity 容器内健康检查：`GET /health/live`、`GET /health/ready`
- 网关存活：`GET /gateway-health`
- MinIO S3：`127.0.0.1:9000`
- MinIO Console：`127.0.0.1:9001`

## 后端测试

```sh
PYTHONPATH=backend python -m pytest backend/tests -q
docker build --target test -t safescan-identity-test \
  -f backend/services/identity-access-service/Dockerfile backend
docker run --rm safescan-identity-test
```

涉及 PostgreSQL/MinIO 的测试必须指向隔离资源，不得使用个人开发库。离线单元测试应通过
依赖注入替换外部模型、对象存储和服务客户端。

## 排障顺序

1. `docker compose config` 检查变量和 Compose 结构。
2. `docker compose ps` 检查 health/status。
3. `docker compose logs --tail=200 <service>` 从入口服务沿依赖方向查看。
4. 使用同一个 `X-Request-ID` 或 correlation ID 串联日志、任务事件和审计。
5. 数据异常先验证 Alembic revision 和 schema，不手工改表绕过迁移。

## 安全约束

- 不提交 `.env`、token、对象存储密钥、真实客户数据或上传媒体。
- PostgreSQL 和管理端口只绑定本机回环地址。
- 所有业务流量通过 Nginx；应用服务不直接暴露宿主机端口。
- 日志和 CI artifact 在上传前必须脱敏。
