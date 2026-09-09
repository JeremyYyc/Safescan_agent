# GitHub CI/CD

## 当前流水线

工作流：`.github/workflows/backend-ci.yml`。

触发范围：

- push 到 `main`、`develop`、`feature/**`、`fix/**`、`refactor/**`、`integration/**`；
- pull request 指向 `main`、`develop` 或 `integration/p0-skeleton`；
- 手动触发。

## Jobs

### docker-compose-smoke

- 使用 `.env.example` 加 CI 专用非敏感变量渲染 Compose。
- `docker compose config` 验证配置。
- 构建 migration runner、Identity、核心领域空骨架、worker、双 BFF、双 React 和 Gateway 镜像。
- 分别运行 identity API 契约/安全单元测试与旧后端完整回归测试。
- 后端镜像显式安装已锁定的 CPU-only PyTorch/Torchvision，避免 CPU Runner 下载无用的
  CUDA 运行库并保证依赖解析可重复。
- 在 Identity test stage 同时运行 `safescan-common` 与 Identity 的单元/API 契约测试。
- 构建并启动 PostgreSQL、Redis、MinIO、migration runner、Identity、核心领域空骨架、worker、
  双 BFF、双 React 和 Gateway。
- migration runner 在空库执行 `alembic upgrade head` 后正常退出，其他数据服务才启动。
- 验证 `/gateway-health`、根路径到 `/tenant/` 的跳转、`/staff/`、Identity guest session、
  BFF 统一 404、各服务 readiness 和 Redis PING。
- 检查目标容器处于 running/healthy；失败时自动输出日志。
- 无论成功失败都执行 `down --volumes --remove-orphans`，不保留 CI 数据。

外部模型密钥在 smoke 中使用哑值，smoke 不发起模型推理。任何需要真实第三方服务的测试应放在
独立、受保护且手动批准的环境，不能阻塞普通 PR。

## 分支和合并建议

- 功能与重构使用 `feature/**`、`fix/**`、`refactor/**`。
- 为 `main`/`develop`/`integration/p0-skeleton` 设置 branch protection，要求 `Docker build and basic functional test`
  通过。
- CI 只验证与构建，不默认发布生产镜像或部署；部署流程应使用 environment protection、
  固定镜像 digest 和人工批准，另建 workflow。

## 本地复现

```sh
docker compose --env-file .env.example config
./scripts/ci/backend-compose-smoke.sh
```

本地 smoke 脚本提供隔离的非生产默认值；也可以通过环境变量覆盖端口和凭据。GitHub Actions
在 job `env` 中提供每次运行独立的 Compose project 名称。
