# SafeScan 日志与审计方案

## 1. 目标和边界

本方案将日志分成两条不可互相替代的链路：

| 链路 | 解决的问题 | 存储与保留 |
|---|---|---|
| 运行日志（observability logs） | 某个请求为何慢、工作流在哪一节点失败、模型/对象存储/数据库是否异常 | JSON 标准输出 → Vector → Loki；热数据 30 天、压缩归档 180 天 |
| 审计日志（audit logs） | 谁在何时进行了登录、上传、删除、下载或权限相关操作 | PostgreSQL `audit_events` 追加写入；在线 1 年，之后归档 3 年 |

日志不是业务数据副本：不得记录密码、JWT、Authorization、Cookie、MinIO 预签名 URL、模型 API Key、完整聊天内容、完整报告内容、视频帧或对象 key。需要定位内容时，记录稳定的 `user_id`、公开资源 ID 和内容长度/SHA-256 前 12 位即可。

## 2. 推荐组件与架构

第一阶段使用以下开源组件，适合当前 Docker Compose 单机部署，也可原样迁移到服务器：

```text
Browser ── request_id ──> Nginx access(JSON) ─┐
                                                ├─> Docker stdout/stderr ─> Vector ─> Loki ─> Grafana
FastAPI ── request_id/run_id ─> JSON 应用日志 ─┘                                  │
                                                                              告警（Grafana Alerting）

需要追责的 API/管理操作 ──> PostgreSQL audit_events（仅追加） ──> Grafana/SQL 导出
```

- **Python：标准 `logging` + `python-json-logger`**。不必为此引入另一套业务框架；封装一个 `app/observability.py`，统一 logger、字段脱敏、异常序列化和审计写入。
- **Nginx：JSON access log**。记录入口状态、耗时和上游耗时，绝不记录 query string（S3 签名会在其中）。
- **Vector**：读取 Docker 容器日志并添加 `service`、`environment`、容器标签；比直接让应用写宿主机文件更容易轮转和集中采集。
- **Loki + Grafana**：Loki 保存高基数字段作为 JSON 内容，标签仅保留低基数的 `service`、`env`、`level`；Grafana 用于搜索、看板和告警。
- **PostgreSQL**：审计事件应与业务数据同库但独立表、独立最小权限账号。数据库或 MinIO 原生日志仍由容器 stdout 进入 Loki，不能充当产品审计日志。

生产环境推荐 Loki 使用 S3/MinIO 后端和持久卷；不要把日志仅保存在容器文件系统。日志链路故障时应用仍应继续服务，运行日志允许丢弃并发出本地告警；审计写入失败则对高风险写操作返回 503 或进入明确的补偿队列，不能悄悄忽略。

## 3. 统一事件格式

所有应用日志一行一个 JSON。时间统一 UTC RFC3339，展示时由 Grafana 转为 `Asia/Shanghai`。

```json
{
  "ts": "2026-09-01T08:15:31.428Z",
  "level": "INFO",
  "service": "backend",
  "env": "production",
  "event": "workflow.stage.completed",
  "request_id": "req_01J...",
  "run_id": "run_01J...",
  "trace_id": "...",
  "user_id": "usr_public_id",
  "chat_id": "chat_public_id",
  "report_id": "rpt_public_id",
  "stage": "detect",
  "duration_ms": 842,
  "outcome": "success"
}
```

必填公共字段是 `ts`、`level`、`service`、`env`、`event`。HTTP 事件再加 `request_id`、`method`、`route`、`status_code`、`duration_ms`；异步/图节点加 `run_id`；认证后的动作加**公开** `user_id`。字段缺失时省略，不写 `null` 占位。

`event` 采用稳定的 `域.对象.动作` 命名，例如 `http.request.completed`、`auth.login.failed`、`storage.object.deleted`、`workflow.stage.failed`、`llm.request.completed`。日志消息只服务人工阅读，查询和告警必须依赖结构化字段/事件名。

## 4. 哪些操作必须记录

| 分类 | 必记事件 | 建议字段 | 级别 |
|---|---|---|---|
| HTTP 网关 | 每个 `/api/*` 请求的完成、5xx、429、上传超限 | request_id、method、route、status、bytes、duration、upstream_duration | INFO；5xx 为 ERROR |
| 认证与账户 | 注册成功/拒绝、登录成功/失败、个人资料修改、token 校验失败 | user_id（失败时仅 email 的 HMAC 指纹）、IP 哈希、user_agent 摘要、reason | INFO；暴力/异常为 WARN |
| 会话与数据 | chat 创建/更新/删除、消息创建、报告引用增删、报告搜索 | actor、目标 public ID、变更前后允许字段、结果 | INFO + 审计 |
| 文件与隐私资源 | 视频/PDF 上传开始/完成/拒绝、资源读取、报告/PDF 下载、对象删除/清理失败 | asset/report ID、MIME、size、SHA 指纹、owner、原因；不写文件名原文或 URL | INFO + 审计（删除、下载、上传） |
| 分析工作流 | run 创建/取消/完成、每个图节点开始/完成/失败、帧数和过滤统计、校验/修复次数 | run_id、stage、duration、frame_count、drop_reason、outcome、error_code | INFO；失败 ERROR；异常质量 WARN |
| 外部依赖 | Qwen 调用、工具调用、Postgres/MinIO 操作的失败、重试、熔断 | dependency、operation、model、timeout、attempt、duration、HTTP 状态；不写 prompt/response | INFO/WARN/ERROR |
| 管理与系统 | 启动/关闭、迁移版本、配置校验失败、健康检查失败、资源耗尽 | release/version、component、reason、usage | INFO/WARN/ERROR |

健康检查成功、模型原始回复、每一帧的调试内容不能默认写入生产日志。`scene_agent.py` 当前的 `SCENE_RAW`/`SCENE_PARSED` `print` 尤其应删除或改成受 `APP_DEBUG_DIAGNOSTICS=false` 控制的脱敏 DEBUG 事件。

## 5. 审计表设计

新增 Alembic 迁移创建如下表；应用角色仅授予 INSERT/SELECT，不授予 UPDATE/DELETE。实际防篡改还需将归档副本写入受限 MinIO bucket 或外部 WORM 存储。

```sql
CREATE TABLE audit_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  request_id text NOT NULL,
  actor_user_id bigint NULL REFERENCES users(id),
  action text NOT NULL,
  resource_type text NOT NULL,
  resource_public_id text NULL,
  outcome text NOT NULL CHECK (outcome IN ('success','denied','failure')),
  ip_hmac char(64) NULL,
  user_agent_hash char(64) NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  prev_hash char(64) NULL,
  event_hash char(64) NOT NULL
);
CREATE INDEX audit_events_occurred_at_idx ON audit_events (occurred_at DESC);
CREATE INDEX audit_events_actor_time_idx ON audit_events (actor_user_id, occurred_at DESC);
CREATE INDEX audit_events_action_time_idx ON audit_events (action, occurred_at DESC);
```

`metadata` 只允许白名单键，如 `reason_code`、`size_bytes`、`mime_type`、`chat_id`、`report_id`、`changes`。`event_hash=SHA256(prev_hash + canonical_event_json + AUDIT_CHAIN_SECRET)` 可用于发现离线篡改；日终将最后 hash 固化到独立对象存储。不能把 IP 明文写入长期审计表，使用轮换 salt/HMAC，安全人员需在 salt 有效期内才可关联请求。

## 6. 实现步骤

1. 在 `backend/app/observability.py` 建立 `configure_logging()`、`get_logger()`、`audit()`；替换 `main.py` 的 `logging.basicConfig`。所有 `print` 改为结构化 logger。
2. 增加 FastAPI middleware：接受可信上游的 `X-Request-ID`，否则生成 UUID7；写入 `request.state` 和 `contextvars`，返回同名响应头；完成时输出唯一的 `http.request.completed`。异常 handler 也写 `http.request.failed`，响应中不泄漏 stack trace。
3. 在 `processVideoStream` 创建 `run_id` 后，把它传入工作流状态与每个 node logger；在 `asyncio`/线程池调用中复制 context，保证同一次分析可按 request/run 搜索。
4. 在认证、上传、下载、删除、会话修改等成功和拒绝分支调用 `audit()`；审计 payload 通过 schema 白名单校验。
5. 配置 Uvicorn access log 为关闭或 JSON 化，避免与 middleware 产生两条不一致的访问日志；添加 Nginx JSON `log_format`，并在 `/gateway-health` 继续关闭 access log。
6. 新增 `observability` Compose profile（Loki、Grafana、Vector），为所有服务增加 `logging` Docker labels（如 `com.safescan.service=backend`）。先在 staging 运行 7 天，校准字段、日志量和告警阈值后再启用生产保留策略。

## 7. 批量查看和调取

### 本机快速排障

```bash
# 某次工作流的所有服务日志（实时）
docker compose logs -f --since=30m backend gateway | jq -c 'select(.run_id == "run_xxx")'

# 过去一小时的所有后端错误，按时间整理
docker compose logs --since=1h backend | jq -s 'map(select(.level == "ERROR")) | sort_by(.ts)'

# 导出单次请求用于工单附件（导出文件受访问控制，不提交到仓库）
docker compose logs --since=24h backend gateway | jq -c 'select(.request_id == "req_xxx")' > incident-req_xxx.jsonl
```

生产环境优先从 Grafana Explore 查询 Loki：

```logql
{service="backend", env="production"} | json | run_id="run_xxx"
{service="backend"} | json | event="workflow.stage.failed"
{service="gateway"} | json | status_code >= 500
```

批量导出通过 Loki HTTP API 分页（按时间窗口分段，避免单次拉取过大），写到加密的受控目录：

```bash
curl --get "$LOKI_URL/loki/api/v1/query_range" \
  --data-urlencode 'query={service="backend",env="production"} | json | level="ERROR"' \
  --data-urlencode 'start=2026-09-01T00:00:00Z' \
  --data-urlencode 'end=2026-09-02T00:00:00Z' \
  --data-urlencode 'limit=5000' > safescan-errors-2026-09-01.json
```

审计记录以只读数据库角色调取，强制时间范围和分页；不要让前端直接查询：

```sql
SELECT occurred_at, request_id, actor_user_id, action, resource_type,
       resource_public_id, outcome, metadata
FROM audit_events
WHERE occurred_at >= :from AND occurred_at < :to
  AND action = ANY(:actions)
ORDER BY occurred_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

建议另做仅管理员可用的 `/api/admin/audit-events` 导出接口：最多 31 天、10,000 行、异步生成 CSV/JSONL，生成物放私有 MinIO、24 小时自动删除，并再次写入 `audit.export.created` 审计事件。

## 8. 看板、告警和保留策略

最小 Grafana 看板：请求量/状态码/p95 延迟；按工作流节点的 p50/p95 与失败数；Qwen 成功率/耗时/超时；MinIO 与 Postgres 失败；上传字节数；审计操作量和拒绝登录数。

初始告警：5 分钟 5xx 比例 >2%；10 分钟 `workflow.stage.failed` ≥3；15 分钟模型超时率 >10%；5 分钟登录失败同一 IP HMAC ≥10；Vector/Loki 无数据 ≥10 分钟；磁盘使用率 >80%。告警消息必须携带 dashboard 链接、`env`、service 和时间窗口，不能携带用户内容。

运行日志：DEBUG 仅开发（7 天），INFO/WARN/ERROR 热存 30 天，压缩归档 180 天；安全审计在线 365 天、归档 3 年（需按所在地法规和实际合规要求确认）；故障工单导出在结案 30 天后删除。每季度抽查一次脱敏规则、恢复一次归档，并测试审计 hash 链完整性。

## 9. 验收标准

- 任意 `/api` 响应含 `X-Request-ID`，以该 ID 能查到入口、应用和错误事件。
- 一次 `processVideoStream` 能以 `run_id` 查看完整节点时序、帧计数、外部调用耗时和最终结果。
- 登录、上传、下载、删除、资料修改及其拒绝路径各产生一条审计事件，且 payload 不含密码、token、URL、原文内容。
- 人为制造 Qwen/MinIO/Postgres 失败后，日志能定位依赖、操作、重试次数和关联请求，客户端仍只收到安全错误。
- Grafana 查询 24 小时 ERROR 日志和导出 10,000 条审计事件可在既定容量目标内完成；应用日志链路中断不影响普通请求，审计高风险写入的失败策略符合预期。
