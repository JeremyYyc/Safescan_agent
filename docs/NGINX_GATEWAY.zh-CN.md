# Nginx 统一代理与组件扩展

本轮分支：`refactor/nginx-gateway`，基于 `refactor/plan@a940dcb`；测试后无快进合并，保留分支。只修改代理/配置/验证，不改变报告生成策略，也不添加 Redis 或 worker 服务。

## 1. 实际入口

```text
浏览器 → localhost:8080 → Nginx :80
                         ├─ /api/*、/health、/health/auth → backend:8000
                         ├─ /gateway-health → Nginx 自身
                         └─ 其他路径 → frontend:80（静态站点或开发 Vite）

后端 MinIO SDK → gateway:9000 → Nginx → minio:9000（S3）
本机 S3 工具 → localhost:9000 ───┘
管理员浏览器 → localhost:9001 → Nginx → minio:9001（Console）

未来：worker/后端 → gateway:6379 → Nginx stream → Redis
      浏览器 → /worker-api/* → Nginx HTTP → 带自身鉴权的管理 API
```

只有 gateway 发布宿主机端口，默认全部绑定 `127.0.0.1`。三种 Compose 组合都保留它，不再通过 test override 绕开网关。8080 应用入口与 9001 管理控制台是独立 origin：控制台只调用自己的 API，应用不跨域调用它。普通用户的图片/PDF 仍从 `/api/assets` 或报告 API 读取，保持 bearer 鉴权，不直接暴露 bucket 或生成前端公开签名链接。

前端 API base 固定为空，所有请求使用同源路径。删除 `CORS_ORIGINS`、`CORS_ORIGIN_REGEX`、`VITE_API_BASE` 的类型/模板/消费代码和 CORSMiddleware；没有改成 `Access-Control-Allow-Origin: *`。同源代理不替代应用鉴权。

## 2. 为什么 S3 独立监听端口

AWS SigV4 签名绑定 Host（包括端口）、原始 URI 和 query。S3 接口不能随意加 `/s3/` 前缀或重新编码路径；因此 Nginx :9000 保持原始请求转发，控制台独立 :9001。见 [MinIO 官方代理说明](https://min.io/docs/minio/linux/integrations/setup-nginx-proxy-with-minio.html)。

`proxy_set_header Host $http_host` 保留端口；`proxy_pass ...$request_uri` 保留原路径/query，不做前缀 rewrite。签名、Authorization、Range 原样传递；没有公开 bucket policy。S3 端口不限 Nginx body size，以支持分段上传；业务 API 仍遵循唯一配置 `MAX_UPLOAD_BYTES` 和后端内存限额。

访问日志仅记录方法、路径、状态和耗时，不含 query/token。S3 server 禁用可能含完整签名 URL 的 Nginx error log，保留状态访问日志；具体错误从 S3 响应检查，避免把签名 URL 写入错误日志。

## 3. 网络、启动与流式处理

| 网络 | 服务 | 用途 |
|---|---|---|
| application | gateway、frontend、backend | HTTP 与后端外部模型访问 |
| storage（internal） | gateway、minio | 后端不在该网络，只能经网关访问 S3 |
| database（internal） | backend、db | 本轮保留 PostgreSQL 内部连接，不发布端口 |

Nginx 使用 Docker DNS `127.0.0.11`、请求时解析上游变量与短期缓存；backend 未运行时 gateway 仍可启动，请求返回 502，不因启动时 DNS 缺失退出。gateway 依赖 MinIO 启动，健康检查同时验证自身和代理后的 MinIO ready；backend 等待 gateway/数据库健康，避免“backend 等 gateway，而 gateway 又等 backend”的循环。

公共代理片段统一 HTTP/1.1、关闭请求/响应磁盘缓冲、较长流式读写超时、禁止自动重放写请求。NDJSON chunk 实时向前端输出；Console/Vite 路由传递 Upgrade/Connection，支持 WebSocket。客户端伪造的 X-Forwarded-For 被网关覆盖；若以后添加上一级可信代理，需要单独配置可信代理链，不能直接信任外部 header。

## 4. 唯一根配置

| 配置 | 默认值 / 含义 |
|---|---|
| GATEWAY_PORT | 8080，应用入口 |
| GATEWAY_S3_PORT | 9000，Nginx S3 入口 |
| GATEWAY_CONSOLE_PORT | 9001，Nginx 管理入口 |
| MINIO_ENDPOINT | gateway:9000，后端 SDK 连接地址 |
| MINIO_BROWSER_REDIRECT_URL | http://localhost:9001，控制台公开跳转地址 |
| NGINX_BACKEND_UPSTREAM | backend:8000 |
| NGINX_FRONTEND_UPSTREAM | frontend:80 |
| NGINX_MINIO_S3_UPSTREAM | minio:9000 |
| NGINX_MINIO_CONSOLE_UPSTREAM | minio:9001 |

修改控制台公开端口时同步修改 redirect URL；容器内端口不变。Compose 把 MAX_UPLOAD_BYTES 传为 NGINX_MAX_BODY_SIZE，不新增重复的容量配置源。Nginx envsubst 仅替换 `NGINX_` 前缀环境项，保留 `$host`/`$request_uri` 等 Nginx 变量。旧本地 CORS/API 地址改为根 env 注释留存，密钥不打印、不提交；同时纠正了根 env 残留数据库主机名 postgres 与当前服务 db 不一致的问题。

启动：`docker compose up --build`。开发：`docker compose -f docker-compose.yml -f docker-compose.test.yml up --build`，地址同为 8080。开发 target 使用 Node 24、Vite 容器内 80、只读源码挂载；不再直接访问 5173，不使用 Vite 的 API proxy。

## 5. Redis / worker 扩展规则

- Redis 是 TCP 协议，使用 `gateway/stream.d/redis.conf.example`。将示例启用为 `.conf` 前，添加 Redis 服务和它与 gateway 共享的内部网络，客户端改成 `redis://gateway:6379`。默认不发布 6379；Redis AUTH/ACL/TLS 仍由 Redis 配置。Nginx 只是转发，不实现持久队列或身份认证。[Nginx stream 官方说明](https://nginx.org/en/docs/stream/ngx_stream_proxy_module.html)。
- 队列 worker 是主动消费进程，通常没有可代理的监听端口。它经上述 Redis 入口接入 broker，不把任务执行过程伪装成 HTTP 转发。
- 若 worker 另有 HTTP 管理 API，使用 `gateway/routes.d/worker.conf.example`，服务自身必须鉴权。示例保留 `/worker-api/` 前缀，实际服务需接受该路径；确需改写时显式调整并测试。
- 两个 `.example` 默认不被 include，不要求不存在的 Redis/worker 启动。配置已做启用状态下的 `nginx -t` 检查，但没有声称 Redis/worker 已实现或运行。

## 6. 代码路径与测试

- `gateway/nginx.conf`：HTTP/stream 顶层、日志、DNS、扩展 include。
- `gateway/templates/default.conf.template`：三个入口和上游路由。
- `gateway/snippets/proxy.conf`：统一头部、超时、流式与缓冲规则。
- `gateway/Dockerfile`：Nginx 1.29（本机验证 1.29.8，内置 stream），模板安装。
- `docker-compose.yml`：网络、唯一端口发布、就绪顺序；test override 仅切换开发前端。
- `backend/tests/test_same_origin.py`：无 CORS/前端地址配置回归。
- `backend/tests/test_gateway.py`：真实 HTTP 代理、流式首块时序、6 MiB S3 multipart、含中文/空格/加号/百分号的 key、预签名 Range、Console HTML。

真实网关测试需显式提供 `TEST_GATEWAY_URL`、`TEST_CONSOLE_URL`；后端固定模型 fixture 使用隔离 `TEST_DATABASE_URL` 和指向 Nginx S3 的 `MINIO_ENDPOINT`。缺少参数会 skip，不能把默认 pytest 结果当作网关验收。测试客户端显式关闭宿主机 HTTP_PROXY，避免误测外部代理。

本轮验证网关及前端镜像构建、三种 Compose 配置、Nginx 实例和完整 Python 回归。外部模型仍用固定响应，不改变既有验证边界；未在日常数据卷上启动全套 Compose，未做真实浏览器 HMR 交互测试。旧隔离 MinIO 使用动态 Console 端口，测试网关通过上游覆盖连接；正式 Compose 固定为 9001。

前端镜像 `npm ci` 报告 15 项既有依赖漏洞（1 low / 5 moderate / 9 high）；本分支没有修改 lockfile 或运行自动升级，需后续独立审计处理。原 macOS PyAV/OpenCV 重复类警告仍存在。
