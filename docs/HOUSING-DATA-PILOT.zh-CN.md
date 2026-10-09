# 单一来源公司的住房多模态试采

日期：2026-09-28。分支：`codex/data-collection-pilot`。

## 已取得的数据

本轮选用 UniLodge 官网作为统一公司来源，取得两个公开项目、八种房型、十三张实际下载的房型图片和五个 Matterport 看房链接。不是生成的图片，也不只是知识文章。

| 项目 | 地址 | 房型 | 下载图片 | 看房链接 |
|---|---|---:|---:|---:|
| UniLodge Kensington | 187 Anzac Parade, Kensington 2033 | 5 | 10 | 5，其中 1 个属于公共区域 |
| Indi Sydney | 298 Pitt Street, Sydney 2000 | 3 | 3 | 0 |

两项目还取得来源页的经纬度、设施名称（分别 15 和 10 项）、房型详情入口和采集时间。它们均列于 UniLodge 官网，因此标记 `source_company=UniLodge`、`relationship=listed_on_company_website`；没有据此声称两个项目的法律产权属于同一实体。

来源：[Kensington](https://www.unilodge.com.au/student-accommodation-sydney/kensington)、[Kensington 相册](https://www.unilodge.com.au/student-accommodation-sydney/kensington/gallery)、[Indi Sydney](https://www.unilodge.com.au/student-accommodation-sydney/indi-sydney)。

## 房型样本

| 房型 | 采集时展示价格原文 | 图片 | 关联 3D 看房 |
|---|---|---:|---|
| Kensington / Twin Studio Apartment | From $588* | 2 | 有 |
| Kensington / Twin Studio Premium | From $606* | 2 | 无 |
| Kensington / 7 or 8 Bedroom Shared Apartment | From $646* | 2 | 有，原文链接名为 8 Bedroom Cluster Room |
| Kensington / Studio Apartment | From $817* | 2 | 有 |
| Kensington / Studio Premium | From $846* | 2 | 有 |
| Indi Sydney / 1 Bedroom Apartment | 当前页未提供 | 1 | 无 |
| Indi Sydney / 2 Bedroom Apartment | 当前页未提供 | 1 | 无 |
| Indi Sydney / 3 Bedroom Apartment | 当前页未提供 | 1 | 无 |

以上是抓取快照，不是实时承诺。房型卡片本身未明确给出周期和按人/按套口径，因此保留原文及数值，`price_period` 和相关口径未擅自填充。搜索缓存与本次直抓的个别价格不同，以样本自己的来源时间为准。

## 多模态范围

- 已下载：13 张 JPEG，共 1,584,043 字节，保存宽高、字节数、SHA-256、原 URL 和本地路径。
- 已收集：5 个 Matterport 外部查看链接，按模型 ID 去重；4 个关联房型，1 个关联公共区域。
- 尚未取得：本地视频文件、独立户型图、PDF 房源手册、精确面积、卫浴数量、具体可租房号和实际空置状态。
- Matterport 是交互看房入口，不是已下载 MP4，也没有抽取平台内部的 3D 资源或全景切片。
- 照片是官方营销/样板展示，不是某个具体房号当前的检查证据。部分照片有人像；本项目现有视频人脸筛选可能剔除此类画面，不能直接当作安全检测评测集。

## 本地文件

数据根目录：`data/collection-pilot/housing-20260928T094923Z/`。

| 文件 | 内容 |
|---|---|
| `preview.html` | 可直接打开的房型图片预览和看房链接 |
| `properties.json` | 2 个项目、地址、坐标、设施和来源 |
| `room_types.json` | 8 个房型、价格原文、字段缺失值和媒体关联 |
| `assets.json` | 18 条媒体记录，包括 13 张图片和 5 个 3D 链接 |
| `housing-summary.json` | 采集数量、缺失项和范围说明 |
| `pages.json`、`raw/` | 页面请求记录、HTML 和 robots 快照 |
| `media/` | 按内容哈希命名的实际图片文件 |

数据目录被 Git 忽略，采集脚本和报告保留在版本管理中；没有导入业务数据库，没有创建真实租约、工单或客户。

## 运行与验证

```powershell
# 新一轮固定 3 页试采；最多下载 16 张关联图片
python scripts/data_collection/housing_collect.py --download-media

# 离线重建已有样本的结构化数据和预览，无网络请求
python scripts/data_collection/housing_collect.py --process data/collection-pilot/housing-20260928T094923Z

python -m unittest discover -s scripts/data_collection -p test_*.py -v
```

复用了原采集器的限速、域名限制、请求数和下载体积限制。页面只访问清单中的 3 页；图片仅从这些页面明确引用的 `image-tc.galaxy.tf` 下载。媒体主机不存在 robots 文件时仅对 404/410 按无规则处理，其他异常停止。图片上限 16 张，每个 Fetcher 仍有 30 请求/50 MiB 预算；页面阶段和媒体阶段是两个独立预算，不是无限抓取。

14 项离线测试通过。新增测试覆盖价格缺失、不臆造周期/房号、准确房型图片匹配、看房去重、公共区域关联、设施与广告分离、稳定 ID 和无结构化数据报错。

实际样本验证：13 张图片均可解码，文件哈希一致；所有房型/图片/看房外键均有效；预览含 8 个房型、13 个本地图片引用，全部文件存在。目视抽查了 Kensington 和 Indi 各一张，内容分别为室内房间及起居室。尚未进行浏览器跨尺寸截图验收或逐张专业核验；外部看房链接只验证来自官方页面，未逐一验证播放器可用性。

## 来源筛选记录

- LIV Mirvac：先取得 3 个候选 HTML 页，确认有楼盘及图片结构；随后在 [使用条款](https://www.livmirvac.com/terms-of-use) 中发现自动采集需事先书面许可，停止继续采集，不下载其媒体，也未纳入本批样本。已有候选快照在 `housing-20260928T094412Z/`，不属于可发布数据。
- UKO：公开房型页很丰富，但 [条款](https://www.uko.com.au/termsandconditions) 对自动提取和数据库用途有明确限制，未用本地采集器抓取房源或媒体。
- UniLodge：本轮公开 robots 允许访问，已查阅公开 [条款](https://www.unilodge.com.au/terms-conditions)。这不等于获得图片开放许可；样本保留本地验证，版权状态标为待确认，规模化复用和对外展示前要确认内容使用范围。

## 如何继续扩大

### 第一步：补全这 8 种房型

沿已发现的公开房型详情链接核对面积、卫浴、价格周期、按人/按套及合同期限。每条补充记录保留字段来源，未知值保持 null。尝试找独立户型图或公开 PDF；播放器链接和可下载视频分开统计。

### 第二步：扩至 5-10 个项目、30-50 种房型

继续限定 UniLodge 公司来源，提前列明允许抓取的项目 URL，按城市或地区分批，每房型最多 3-5 张图片。保留主体经营/管理关系证据；品牌、管理方、法律所有人分列，不能把“同站展示”扩大成“同一产权公司”。

在扩大前完善：项目级失败继续执行和汇总、跨运行资产缓存与内容版本、变化检测、缺失率统计、媒体关联人工抽检、许可/访问条件记录。当前工具适合固定样本，尚非生产级批量采集器。

### 第三步：再做批量更新

目标应以实际可核验的目录为准，不预先承诺可取得多少独立房号。先按 20 个项目分批检验，再考虑全目录；详情和价格按变化更新，图片按哈希复用。扩到新地区时不能直接套用前一轮 NSW 知识规则。

### 接入本项目

当前 `Property` 表偏向具体出租单元，本批 `room_type` 不能直接当八个真实房号。建议先作为来源目录导入暂存层；需要演示申请/租约/维修时，再从房型生成明确标记为 synthetic 的演示单元。保留真实房型及媒体来源，但不声称这些模拟租约发生在真实房源。
