# 区域采集续作记录

日期：2026-09-30。分支：`codex/data-collection-pilot`。

## 本轮结果

完成中断批次的逐图复核，补采 16 张图片，将三城批次与 Flagstaff 已验收快照合并。新快照独立保存，9 月 29 日原始文件未覆盖。

| 城市 | 楼盘 | 房型 | 报价 | 核心完整 | 含人物补充 | 核心且至少两张室内图 |
|---|---:|---:|---:|---:|---:|---:|
| Adelaide | 1 | 9 | 13 | 9 | 0 | 6 |
| Brisbane | 1 | 12 | 26 | 3 | 0 | 1 |
| Melbourne | 2 | 12 | 24 | 2 | 6 | 1 |
| 合计 | 4 | 33 | 63 | 14 | 6 | 8 |

核心完整要求至少一张完整布局示意图和一张清晰无人物室内图。含人物补充集另有 6 条，两组互斥；因此共有 20 条具有完整布局和室内图片的房型组合。另有 13 条待补齐。此口径不等于旧 Flagstaff 验收的“两张室内图且有报价”，报价缺失不影响本轮媒体完整性。

68 个不同哈希的图片文件在页面上被引用 69 次。哈希去重仅识别完全相同的文件，不代表不同哈希一定是不同场景。图片按来源房型区块或图库标签关联，仍是样板资料，不能证明具体房号的实际状态；South Bank 的 Ensuite 与 Multishare 共用一张卧室图，记录中保留共用关系。

## 已修复与缺口

- Melbourne Central 的 Studio Queen 和 2 Bedroom Apartment 原图下边缘被 CDN 裁切。本轮从同一公共资源请求移除 crop 参数的版本，取得 1920×1357 完整图；原裁切图保留并标注。请求变换和原 URL 记录在 selections.json。
- 墨尔本若干图片含人物，另有 300×150 缩略图；人物图单列补充层，缩略图和床品特写不进入核心室内图集合。
- Metro Adelaide 的 9 个房型都有布局和室内图片。Deluxe Balcony 的描述为 32 SQM，图纸标注 Apartment 40m2，差异保留在 quality_notes，未擅自统一。
- Melbourne Central 两卧图纸的 8m2 是私人卧室面积，不能替换页面的约 26m2 整套面积。
- 4 条 Melbourne Central 房型记录有公开楼层范围。所有具体分配楼层、房号仍未知。
- 剩余 13 条包括 South Bank 9 条、Melbourne Central 3 条、Flagstaff Queen 1 条，需继续查找可明确关联的完整布局图或补齐媒体。没有将相似房型布局直接复制给这些记录。
- 报价保留 9 月 29 日原快照时间，本轮没有刷新报价。币种和计价对象未确证的字段继续为空。

## 产物

- 汇总预览：`data/collection-pilot/unilodge-catalog-20260930/index.html`。
- 全部房型：同目录 `dataset.json`；核心完整集 `complete_room_types.json`；含人物补充集 `supplementary_room_types.json`；待补集 `incomplete_room_types.json`。
- 独立报价：`offers.json`；按区域汇总：`summary.json`；输入、输出和图片哈希：`manifest.json`。
- 自包含图片：同目录 `media/`，可随汇总目录一起备份和离线浏览。
- 三城续采快照：`data/collection-pilot/unilodge-regional-dataset-20260930/`，包含新增网络响应、复核文件及 `gaps.json`。
- 逐图判读配置：`scripts/data_collection/unilodge_regional_reviews.json`，以内容 SHA256 绑定判读。

汇总包只是整理后的浏览与数据入口；重建时仍需保留三城原始 HTML、续采快照和 Flagstaff 验收目录。数据目录被 Git 忽略，提交代码不会自动备份数据。本轮未提交或推送 Git，未写入业务数据库。

## 复算与验证

```powershell
# 已有续采目录仅更新离线导出，不再次请求网络。
python -X utf8 scripts/data_collection/unilodge_resume.py --output data/collection-pilot/unilodge-regional-dataset-20260930 --export-only
# 汇总输出目录必须不存在。
python -X utf8 scripts/data_collection/unilodge_catalog.py --output data/collection-pilot/unilodge-catalog-replay
python -m unittest discover -s scripts/data_collection -p "test_*.py"
python -m unittest discover -s scripts/data_analysis -p "test_*.py"
```

采集测试 38 项、分析测试 26 项通过；之前分析测试的临时目录错误在正常文件权限下没有复现。本轮 7 个汇总文件与 68 个媒体文件哈希全部通过，图片解码通过。浏览器 1440×1000 和 390×844 检查无页面级横向溢出，69 处图片引用无损坏，Melbourne + core 筛选为 2 条。截图在汇总目录 desktop.png、mobile.png。临时 HTTP 服务的 favicon.ico 返回 404，不影响媒体或筛选。

## 下一批

先以这 20 条媒体组合为可检查批次，再选择新的楼盘扩大三个城市覆盖。每个楼盘先确认房型与布局关联再下载，优先原始完整图、多角度室内图及报价依据。继续按房型计数，不以报价租期或相同图片复制凑到 100 条；用途授权、独立人工签认与业务发布状态仍未完成。
