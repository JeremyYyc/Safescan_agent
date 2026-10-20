# 数据采集流程与结果

更新日期：2026-10-09。采集阶段已结束，当前交付按“有本地图片即可”收录，不要求布局图、室内图或其他字段全部齐全。

## 最终交付

2026-10-20 新增 [PostgreSQL + MinIO 交付](../../outputs/sql-minio-dataset-20261020/README.md)：
一个 `dataset.sql` 存储四套数据及图片对象索引，图片通过随包脚本上传到 MinIO。
[完整 SQL/图片包](../../outputs/sql-minio-dataset-20261020.zip)。
生成脚本 `export_sql_delivery.py`，上传逻辑 `upload_dataset_minio.py`，离线测试 `test_sql_delivery.py`。
使用独立 `collected_data` schema，不自动接入应用业务表。

除下列三套图片数据外，另有[第四套知识文档](../../outputs/knowledge-documents-20261009/README.md)：11 篇、5,899 个英文单词、62 个教程步骤，包含总表、正文、原始快照和离线预览。[下载知识文档包](../../outputs/knowledge-documents-20261009.zip)。整理脚本为 `summarize_knowledge_docs.py` 和 `package_knowledge_docs.py`。

交付目录：[outputs/collected-data-20261009](../../outputs/collected-data-20261009/)。

| 数据 | 带图记录 | 独立图片 | 数据包 |
| --- | ---: | ---: | --- |
| 维修图片 | 59 | 75 | [repair.zip](../../outputs/collected-data-20261009/repair.zip) |
| 学生公寓 | 29 | 81 | [student.zip](../../outputs/collected-data-20261009/student.zip) |
| 社会公寓 | 29 | 183 | [general.zip](../../outputs/collected-data-20261009/general.zip) |

共 339 张独立图片。记录不是统一的实物单位：维修包括帖子和缺陷图片记录；住房包括房型及具体房源。同一图片可关联多个房型，不能用图片关联数代替独立图片数。

每套目录包含：

- `总表.xlsx`：总表、图片索引两个工作表。
- `总表.csv`、`图片索引.csv`：可直接导入的数据表。
- `images/`：实际图片，按 SHA256 命名，关联关系查图片索引。
- `records.json`、`images.json`：结构化记录及图片关联，保留原始字段。
- `source_metadata/`：来源批次的 JSON 元数据。
- `index.html`：离线图文预览，直接用浏览器打开。
- `manifest.json`：交付文件的 SHA256 校验清单。

## 采集流程

1. 从公开页面或公开 API 发现房型、房源和维修帖子，保存来源链接及采集时间。
2. 保存原始响应，提取房型、地址、报价、症状和图片链接。缺失字段不补造。
3. 按明确图片链接下载，保留成功和失败日志、图片尺寸、哈希及来源关联。
4. 前期做过布局与室内图匹配、维修类型与图片的轻量目视核验，生成精选版和补充项。
5. 最终改为全量交付：收回以前因完整度或图片内容而未入选的已下载图片，只排除用户明确要求移除的 5 张藻斑。字节完全相同的图片每套仅存一份，保留关联。
6. 校验图片解码、哈希、表格行数、关联路径和压缩包完整性，再交付三套数据。

原始批次保存在 [data/collection-pilot](../../data/collection-pilot/)，最终整理不覆盖原始批次。自行生成的核验拼图和界面截图不作为爬取图片收录；未成功下载、仅有链接的图片不计入交付数量。

## 脚本入口

| 环节 | 主要脚本 |
| --- | --- |
| HTTP 请求、访问限制、基础采集 | `collect.py` |
| 学生公寓试采与区域扩采 | `housing_collect.py`、`flagstaff_collect.py`、`unilodge_regions.py`、`unilodge_regional_media.py` |
| 学生公寓目录与预览 | `unilodge_catalog.py`、`unilodge_preview.py` |
| HOME、Novus 与其他社会房源 | `home_collect.py`、`novus_collect.py`、`general_batch.py`、`verify_general_housing.py` |
| 初期维修来源与 BD3 | `repair_pilot.py`、`repair_bd3_pilot.py` |
| DIY Stack Exchange 室内报修 | `indoor_repair_collect.py` |
| 在用灯具、洗衣机、马桶补采 | `collect_used_fixtures.py` |
| 历史精选与核验导出 | `review_indoor_repair.py`、`review_bd3_export.py`、`integrate_repairs.py` |
| 三套全量数据整理 | `package_all_collected.py` |
| 交付校验与 ZIP 打包 | `verify_package_delivery.py` |

Excel 生成脚本单独保存在交付根目录的 [build_workbooks.mjs](../../outputs/collected-data-20261009/build_workbooks.mjs)，使用 Codex 内置 `@oai/artifact-tool`，不是项目应用的运行依赖。

## 运行说明

从仓库根目录运行 Python 脚本。依赖见本目录 `requirements.txt`。不要为了查看交付结果重新运行爬虫。

室内报修采集分阶段运行：

```powershell
python scripts/data_collection/indoor_repair_collect.py discover
python scripts/data_collection/indoor_repair_collect.py download
python scripts/data_collection/indoor_repair_collect.py export
```

以上示例用于说明顺序。部分采集器使用固定批次目录，已有目录会被拒绝；如需新采集，应先调整为新的批次输出路径，不删除旧批次强行重跑。HTTP 403、429 或 robots 拒绝的来源不绕过。

已有原始数据的离线交付顺序：

```powershell
python scripts/data_collection/package_all_collected.py
# 然后使用内置 Node 与 artifact-tool 运行 build_workbooks.mjs，生成三份 Excel。
python scripts/data_collection/verify_package_delivery.py
```

离线整理脚本会重新生成固定交付目录下的表格输入和数据文件；Excel 需在打包前重新生成，避免与更新后的 JSON 不一致。当前已生成的交付包无需重跑。

## 使用边界与项目改动

- 学生公寓大多是房型展示图，不代表已分配房号或当前空房。
- 社会房源保留历史已出租、背景、示意及尚未核验的照片，报价不代表当前有效报价。
- 维修照片可仅显示相关设备或部件。症状来自原帖，不能把图片关联等同于确诊或真实工单。
- 原作者、来源、许可及权属待确认信息保留；未统一认定为可自由再发布的图库。
- 本轮未修改应用业务逻辑、未导入生产数据库。采集与分析脚本是新增工具目录，原有 `scripts/ci` 未改动。
- 校验结果见交付目录的 `delivery_validation.json`；覆盖盘点见 `coverage_audit.json`。

## 进一步阅读

- [最终交付说明](../../outputs/collected-data-20261009/README.md)
- [早期采集说明](README.md)
- [数据分析脚本说明](../data_analysis/README.md)
- [历史分析报告目录](../../docs/data-analysis/)

历史报告反映当时的精选与完整度统计，数量可能小于本次全量交付。最终数量以交付目录 `summary.json` 为准。
