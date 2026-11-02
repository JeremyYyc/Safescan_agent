# 手动数据同步

部署只升级数据库结构、启动应用与业务 worker，不执行员工 seed、业务数据导入、媒体上传、城市重新分配或合同批量生成。`IDENTITY_SEED_STAFF=true`、`PROPERTY_LEASING_SEED=true` 也不会触发启动导入。

统一入口是 `scripts/data/sync.py`。默认 dry-run 只检查本地必需文件并打印执行计划，不访问 Docker、数据库或网络，也不创建输出目录。

```sh
# 先审阅计划；源目录必须是本机现有解压后的执行数据导出。
python3 scripts/data/sync.py --source-dir /path/to/execution-export --dry-run

# 明确应用：员工 -> 业务数据 -> 图片 -> 城市分配 -> 合同 PDF。
python3 scripts/data/sync.py --source-dir /path/to/execution-export --apply

# 只补合同，或只同步指定步骤；参数顺序不会改变依赖顺序。
python3 scripts/data/sync.py --steps lease-pdf --apply
python3 scripts/data/sync.py --source-dir /path/to/execution-export --steps media,city --apply
```

应用使用现有 Compose 服务镜像运行一次性容器，源目录只读挂载，沿用同一根环境配置与私有 MinIO 网关。请先执行 Alembic migration 并确保现有部署的数据库、Identity、MinIO 和 Gateway 正常；工具不会启动、重建或升级服务。若实际根环境文件或项目名不同，显式传入 `--env-file /path/to/.env --project-name safescan_agent`；密钥值不打印。

| 步骤 | 输入与行为 | 重复执行 |
|---|---|---|
| `bootstrap-admin` | 可选；按根环境配置创建首位管理员，不在默认步骤或 `all` 中 | 已有账号保留 |
| `staff` | 手动补充 16 个开发／测试员工；生产禁止 seed | 不重置密码、不覆盖现有城市或权限 |
| `collection` | `dataset.sql`、`manifest.json`、`objects.json` 的原始采集导出；审计后更新独立 `collected_data` 表 | 固定键 upsert；不写业务房源／工单表 |
| `dataset` | 11 个 JSONL 执行表；验证关联、来源和时间线，编译受控 SQL | 仅插入缺失记录；保留已有运行状态，身份／归属或签约条款冲突报错并回滚 |
| `media` | `objects.json` 及引用文件；先检查路径、长度与 SHA-256 | 已有对象读取完整字节核验；不同内容拒绝覆盖 |
| `city` | `execution_units.jsonl`、`housing_records.jsonl` | 事务内补城市、修复跨城分配并写审计；第二次无变更 |
| `lease-pdf` | 数据库现有租约与官方模板 | 精确 fingerprint 的对象存在则跳过，缺失则生成 |

新建图片 bucket 需显式添加 `--create-buckets`；创建的 bucket 保持私有。如需同步原始采集包，单独指定它，避免把执行数据导出当作原始七表格式：

```sh
python3 scripts/data/sync.py --source-dir /path/to/execution-export \
  --collection-dir /path/to/raw-collected-export --steps all --dry-run
python3 scripts/data/sync.py --source-dir /path/to/execution-export \
  --collection-dir /path/to/raw-collected-export --steps all --create-buckets --apply
```

同时指定两种导出时，`media` 会分别校验、上传两个包的清单。输出 SQL、审计和报告保存在 `output/data-sync/`，可用 `--output-dir` 修改；不写入源目录。失败立即停止，修复原因后可选择失败步骤重新运行，不需要重置数据库。事务保护只覆盖各数据库步骤；已经完成的私有媒体上传不会因后续步骤失败而删除。

合同 watch 不属于默认部署。只有明确运行 `docker compose --profile data-sync up -d property-leasing-document-worker` 才启用；停止使用 `docker compose --profile data-sync stop property-leasing-document-worker`。正常人工同步只运行一次 `lease-pdf` 步骤。

## 本次代码来源

仅整合当前本地待提交更新：`c04f` 的执行数据生成／字段补全／媒体／打包工具，`53f1` 的城市感知导入与城市协调工具，`4865` 的原始采集审计与导入编译器。重叠文件采用 `53f1` 的城市版本。没有合并旧远程采集分支，没有复制真实 `.env`、凭证或 865 MB 数据包；已有源目录原样保留。

`safescan_common.cities` 依赖来自同批本地城市架构更新，随服务镜像安装；SQLAlchemy、psycopg、MinIO 与 Pillow 复用现有服务依赖。原始导出的已识别 schema/header 与 manifest 仍严格核验；格式变更应先更新审计／编译器，而不是直接执行源 SQL。

## 验证与扩展

```sh
PYTHONPATH=backend/packages/safescan-common/src:scripts/data \
  python3 -m pytest -q scripts/data
```

本地需 pytest、SQLAlchemy、psycopg 等现有后端开发依赖，也可使用 Property 测试镜像并将整个仓库只读挂载到 `/workspace`，保持原有目录层级。
`test_city_assignments.py` 的真实数据库场景仅在显式提供隔离的 `TEST_DATABASE_URL`、`CITY_DATASET_ROOT` 时运行。
CI 另由 `scripts/ci/data-sync-postgres-test.sh` 创建、迁移独立 `manual_sync_test` 库，显式 seed 16 个员工，验证重跑不复活已结束租约的占用位，保留修改后的租金与合法未来城市交接；结束自动删库。集成测试禁止指向日常业务库。全量合同只读验收使用 `scripts/ci/verify-lease-pdf-storage.py`。

增加同步步骤时，在 `sync.py` 的有序 `STEPS` 中声明服务与说明，补预检和一次性容器命令，并在 `sync_worker.py` 实现对应事务／幂等动作。不要把入口加入 Docker CMD、Compose command、应用 lifespan 或 migration 的内容导入中。
