# Report 存储改造执行清单（工程最优）

## 目标
- 保留 `reports.id` 作为统一主键，最小化 API 变化。
- 将“分析报告”和“PDF 报告”拆到类型子表，消除主表混杂字段。
- 新增统一 `files` 表，避免路径散落在多个字段/JSON 内。

## 分阶段执行顺序

### Step 1：结构准备（不切读写）
- 执行迁移脚本的 schema 阶段，创建新表：
  - `files`
  - `report_analysis`
  - `report_pdf`
  - `report_assets`
- 在 `reports` 增加新列：
  - `report_kind`（`analysis` / `pdf`）
  - `origin_chat_id`
  - `title`
  - `status`

### Step 2：历史数据回填（可重复执行）
- 从旧 `reports` 读取数据，回填到新结构：
  - `report_kind/origin_chat_id/title/status`
  - 分析报告写入 `report_analysis`
  - PDF 记录写入 `report_pdf`
  - 视频/图片/PDF 文件路径收敛到 `files`
  - 代表图写入 `report_assets`
- 该阶段可多次执行，脚本通过 UPSERT 保证幂等。

### Step 3：一致性核对
- 校验总量与分型数量是否匹配：
  - `reports` 总数
  - `analysis` 数量与 `report_analysis` 数量
  - `pdf` 数量与 `report_pdf` 数量
- spot-check 若干 chat 的历史展示、PDF 下载、report ref 行为。

### Step 4：应用切换（代码层）
- 先将读路径切换到新结构（`report_analysis/report_pdf/files`）。
- 稳定后再切写路径。
- 过渡期可保留旧字段写入，直到确认不再依赖。

### Step 5：收尾（可选）
- 完成观察期后，删除旧混杂字段或将其降级为兼容只读。
- 补充索引与慢查询优化。

### Step 6：最终去兼容（推荐在稳定后执行）
- 先预演旧列删除检查：`python backend/scripts/drop_legacy_report_columns.py`
- 再正式删除旧列：`python backend/scripts/drop_legacy_report_columns.py --apply`
- 如校验提示不通过但你确认可删，可执行：`python backend/scripts/drop_legacy_report_columns.py --apply --force`

## 实施命令
- 预演（不写库）：`python backend/scripts/migrate_reports_storage_v2.py`
- 正式执行：`python backend/scripts/migrate_reports_storage_v2.py --apply`
