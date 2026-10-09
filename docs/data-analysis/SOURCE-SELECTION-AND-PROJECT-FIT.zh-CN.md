# 房源来源选型与项目结构适配报告

核验日期：2026-09-29。范围：公开房源基本字段、户型图、室内图及视频入口；不含住户信息、登录后台、申请表提交或维修系统。

## 1. 结论

**学生公寓优先 UniLodge；普通租赁公寓优先 Novus Australia。** 这是基于本轮公开页面和小样本的技术适配选型，不是无条件批量采集或内容再利用许可。

- UniLodge 已有可复用解析器，房型、租期报价、布局图、室内图、VR 能组成房型样例；适合补充学生公寓与合租场景。缺点是房型不是具体房号，部分面积是单间面积，报价可能按人计。
- Novus 样例具有具体房号、卧卫、车位、周租、对应房号的清晰户型图和高分辨率室内示意图，比本轮 HOME 样例更接近项目 `Property`。优先验证其授权范围及完整库存出口，再决定扩采。
- **没有一个候选已被证明能不受限制地获取并复用 100 条以上完整独立房源。** 楼盘规模超过 100 套、首页出现若干房源、实际获准采集 100 条，是三个不同指标。
- 两套样例已完成文件校验及助手视觉复核；独立人工确认、内容复用授权、生产导入均未通过。没有取得可直接用于巡检的视频文件。

这里“普通/社会公寓”指面向一般租客的市场化租赁公寓，主要是机构运营的 Build-to-Rent，不是澳洲政策意义上的 social housing。本轮也不能代表独栋、联排、老旧住宅等全部普通住房。

## 2. 项目需要什么

以实际代码为准，而非仅看设计文档：

| 消费位置 | 实际要求 | 采集适配判断 |
|---|---|---|
| `Property` | reference、address、bedrooms、bathrooms、weekly_rent、currency、status、listing_visibility | 网页字段需规范化；内部状态不能从“可预订”直接映射 |
| 房源元数据 | parking_spaces、floor_area_sqm、成对经纬度、图片 URL 数组、单个 floorplan_url | 车位未知不是 0；面积口径必须额外保留 |
| 前端房源图片 | 使用展示图片；当前房源卡片以封面展示为主 | 不能把 logo、大堂、营销横幅混作房屋内部照片 |
| 巡检报告上传 | 上传实际 `video/*` 文件，关联报告与房源，保存对象存储信息 | Matterport/YouTube 链接不能当成上传文件，更不是巡检证据 |
| 维修/租赁流程 | 工单、人员、合同、状态与时间信息 | 本轮公开房源不提供这些事实；另建明确标记的测试数据 |

关键代码：[Property 模型](../../backend/services/property-leasing-service/app/models/tables.py)、[车位迁移约束](../../backend/alembic/versions/20260914_0013_property_parking_legacy_compat.py)、[元数据约束](../../backend/alembic/versions/20260910_0007_property_metadata.py)、[目标 schema](../../backend/app/persistence/target_schema.py)、[巡检文件上传](../../backend/services/inspection-report-service/inspection_report_service/service.py)、[房源展示组件](../../frontend/apps/staff-web/src/components/PropertyVisual.tsx)。

**容易漏掉的约束：** ORM 中 `parking_spaces` 可空是为了兼容历史房源；迁移触发器要求新增房源及明确编辑元数据时不能为空。本轮 UniLodge 缺车位，不能作为完整事实直接新增。

当前 `Property` 没有独立的房型实体、多租期报价、面积口径及媒体来源字段。保留暂存层 `room_type / unit_listing / offer / media` 分离；演示投影将来源和假设放进 `attributes`，不修改生产表以迁就爬虫。

## 3. 来源横向比较

证据等级：A = 本地固定页面解析、媒体下载及助手视觉复核；B = 官方页面/条款核查，未完成本地媒体样例。不同等级不能直接比较“图片完整率”。未验证项记未知，而不是零。

| 来源 | 规模证据及口径 | 基本数据与多模态 | 本轮验证 | 主要限制与选择 |
|---|---|---|---|---|
| UniLodge | 官网称澳新超过 110 个物业地点，非 110 个房号 | 房型、面积、分租期报价、布局图、室内照片；部分 VR | A；Flagstaff 固定目标 5 房型、7 报价；其中 1 房型完成媒体样例 | 首选学生来源；仍需房型/房号分离及授权确认 |
| Scape | 官方 2025 行动计划披露 19,000+ 床位、39 栋，非在租库存 | 房型、租金、房间图等；没有取得本轮完整附件包 | B；公开房型及条款研究 | 私有电子检索系统也受许可限制；不作为默认扩采来源 |
| Iglu | 官方招聘页称近 6,000 床位、14 个运营项目；开发中库存另计 | 房型、面积、房间图、户型图、资料 PDF、视频入口 | B；Brisbane City Premium Studio 页面核查 | 多模态候选较强，但本轮未闭环报价和媒体关联；复制权限受限 |
| HOME | Docklands 项目 676 套，来自项目建筑方 | 房型详情可带多个房号报价；室内、公共设施、宣传图混合 | A；历史 C04 样例 + 本轮 4 个索引页 | 保留对照；已取户型图清晰度偏弱，不等于全站原图都差 |
| LIV by Mirvac | 官方 LIV Munro 490 套 | 单元、卧卫、面积、价格、户型图，结构适配度较好 | B；公开列表和条款核查 | 明确要求机器人及人工提取事先书面许可；未启动自编采集器 |
| Indi | 官方 Footscray 702 套、Southbank 434 套 | 项目/房型介绍、照片、平面图与 VR 入口 | B；动态房源列表尚未验证完整单元出口 | 浏览器工具超时不代表网站封禁；用途与复制授权未解决 |
| Novus Australia | 2022 官方建设公告称 Sturt 173 套；现有项目页已提供租赁入口 | 具体房号、卧卫车位、周租、清晰图纸、高清内部示意图、楼盘视频入口 | A；索引首响应 8 个独立挂牌链接，完成 1 套详情及媒体样例 | 首选普通公寓技术来源；173 为历史项目规模，非当前可抓套数 |

规模与页面来源：[UniLodge 地点](https://www.unilodge.com.au/student-accommodation-australia)、[Scape 官方行动计划](https://www.scape.com.au/wp-content/uploads/2025/12/Scape-GBV-Action-Plan.pdf)、[Iglu 运营规模](https://iglu.com.au/careers/)、[Iglu 房型](https://iglu.com.au/rooms/brisbane/brisbane-city/premium-studio-apartment-bc/)、[HOME Docklands 项目](https://www.coxarchitecture.com.au/project/home-docklands/)、[LIV Munro](https://www.mirvac.com/investor-centre/property-portfolio/build-to-rent/liv-munro)、[Indi Footscray](https://www.indi.com.au/indi-footscray)、[Indi Southbank](https://www.indi.com.au/indi-southbank)、[Novus 173 套建设公告，2022-08-01](https://www.novusaus.com/news/southbank-project-novus-on-sturt-officially-breaks-ground)、[Novus Sturt 当前项目入口](https://www.novusaus.com/location/novus-on-sturt)。

不设看似精确的综合分数：当前各来源采样深度不一致，评分会把“尚未取样”误当作“数据差”。选型顺序为：用途准入门槛 → 房源粒度 → 多模态可用性 → 字段适配 → 可验证库存 → 采集维护成本。用途门槛尚未通过的来源只能推荐进入下一轮验证，不能发布。

## 4. 权限与采集边界

“非商业”“公开可访问”“robots 允许/不存在”都不等于拥有复制、建库、展示或训练授权。以下是条款审查记录，不是法律意见。

| 来源 | 当前用途边界 | 执行决定 |
|---|---|---|
| UniLodge | 本轮未获得开放数据或媒体复用许可 | 保留研究样例，正式入库/公开展示/批量扩采前确认授权 |
| Scape | 8.2 限定个人摘录条件；8.3 对其他网站及公私有电子检索服务要求书面许可 | 不以“私有 RAG/非商业”为理由直接扩采 |
| Iglu | 内容复制受版权与书面许可条件约束 | 仅作为比较候选，不扩下载附件 |
| HOME | 未确认涵盖批量采集及项目展示的许可 | 既有样例不自动转为获准资产 |
| LIV | 自动工具或人工监测、复制、提取均要求事先书面许可 | 暂不扩采 |
| Indi | 复制、改编等用途受条款限制；没有开放数据许可证据 | 暂不扩采 |
| Novus | 允许个人非商业下载，但禁止修改及后续复制，且有澳洲居民适用范围声明 | 只保留本次研究证据；不声称项目建库、对外展示、第三方 AI 处理或批量采集已获准 |

条款：[UniLodge](https://www.unilodge.com.au/terms-conditions)、[Scape](https://www.scape.com.au/terms-and-conditions/)、[Iglu](https://iglu.com.au/terms-conditions/)、[LIV](https://www.livmirvac.com/terms-of-use)、[Indi](https://www.indi.com.au/terms-and-conditions)、[Novus](https://www.novusaus.com/terms-of-use/)。Novus 第三方图片托管并不证明对方授予本项目再利用权；使用人的适用条件也未核实。

本轮固定清单、白名单域名、请求量/响应体上限、robots 检查、403/429 停止；未登录、绕过验证码、提交申请、调用住户后台或遍历隐藏接口。Novus/部分图片域 robots 返回 404，记录为不存在规则而不是授权。原始页面和图片保留在 Git 忽略目录，未加入公开资源库。

## 5. 实际样例

### 5.1 UniLodge Melbourne Flagstaff

[原始 Studio 页面](https://www.reserve.unilodge.com.au/categoryInfo.html?category=488)，样例为 Studio Standard。Flagstaff 是 UniLodge 的具体公寓项目，不是独立平台。

| 字段 | 观测与处理 |
|---|---|
| 实体 | 房型；没有具体房号，不虚构真实库存 |
| 地址 | 楼盘结构化数据：17 Wills Street, Melbourne, 3000 |
| 卧卫 | Studio 规范为 0 个独立卧室；文字 private ensuite 规范为 1 卫 |
| 面积 | 13㎡，页面按 studio 表述，未明确室内/总面积细分 |
| 报价 | 509 / 529 / 539 每周，分别对应不同租期；只有 `$`，币种仍待确认 |
| 演示选价 | 509，保留 Full Year Semester 1 2027 条件；表单起止日期不是确认合同 |
| 车位 | 未知，事实层保持 null |
| 户型图 | 1920×1080，完整 3D 布局渲染图；没有尺寸标注，不作为测量图 |
| 室内图 | 卫浴、床/书桌/厨房两张，均 1024×400；通用样板间照片 |
| 视频/VR | Matterport 入口；没有下载视频，没有验证连续巡检内容 |

第一次取到 1040×400 的布局缩略图，边界被裁切，未采用；随后使用楼盘页面实际链接的完整布局图。另两张有人物的生活方式图片未入最小房屋图片集合。不是通过增加营销图片数量来“提高完整率”。

### 5.2 Novus on Sturt

[原始 302 房源](https://www.novusaus.com/find-your-home/novus-on-sturt/IRE4925059)。Novus 是机构租赁公寓运营品牌，并非汇总多个房东的通用租房门户。

| 字段 | 观测与处理 |
|---|---|
| 房源标识 | IRE4925059；地址 302/153 Sturt Street, Southbank VIC |
| 卧卫车位 | 1 卧、1 卫、0 车位；0 是页面明确值，不是缺失补零 |
| 周租 | `$675 per week`；币种待确认，租期条件未知 |
| 面积 | 网页 50㎡；图纸明确室内 44㎡、阳台 6㎡、合计 50㎡ |
| 户型图 | 3508×2480；图上 Apartment 302 与地址一致 |
| 室内图 | 抽取两张 8192×5464 的起居/餐厅/厨房图片 |
| 图库规模 | 34 个不同媒体 URL 候选；只下载并审核其中户型图和两张室内图，不等于 34 张已验证室内图 |
| 视频入口 | 页面存在 YouTube 楼盘视频链接；未下载、未验证可播放性及房号关联 |
| 可入住信息 | 原文日期为 2025-11-03，早于采集日；不据此判断当前仍可租 |

**面积处理：** 暂存层保留页面 50；演示投影选择图纸识读的室内 44，并在 `attributes` 保存 44+6=50 的口径及复核状态。项目现有字段本身未定义统一内外面积标准，因此这是明确记录的投影约定，不是声称现有数据库规定必须填室内面积。图纸识读尚需独立人工确认。

**图片关联：** 户型图房号可以对上，但网页声明图库为示意照片，可能并非具体该户型。不得把这些图片包装成 302 室的现状或安全检查证据。

## 6. 校验结果与指标

本轮分母仅为新建两套样例，不并入早先 9 房型基线，不用楼盘总量填充分母。

| 指标 | 本轮结果 | 解释 |
|---|---|---|
| 下载图片文件完整性 | 9/9 | 实际解码、尺寸及 SHA-256 校验通过 |
| 图片内容去重 | 9 个不同 SHA-256 | 不是对 URL 去重；不代表语义内容都不同 |
| 最小媒体集合 | 2/2 样例 | 每套 1 张布局图 + 2 张室内图；助手审核候选 |
| 采用图片 | 6/9 | 排除 1 张裁切图、2 张生活方式人物图 |
| 独立人工通过的媒体 | 0/9 | 助手判读不能代替人工签认 |
| 当前具体单元实况证据 | 0/2 样例 | 房型图库/示意图库不满足这一要求 |
| 带测量面积的图纸 | 1/2 样例 | Novus 有可读面积标签；UniLodge 仅布局 |
| 实际巡检视频文件 | 0/2 样例 | VR/视频链接另存，不能抵充文件 |
| 已观测字段直接投影通过 | 0/2 | 缺内部状态、币种确认；UniLodge 另缺房号及车位 |
| 标明模拟字段后的离线规则通过 | 2/2 | 不是数据库插入成功，也不是获准发布 |
| 应用复用权限通过 | 0/2 | 保持 not_released |

HOME 索引复算：Docklands 11 房型卡/13 可租数量标记、Richmond 6/9、Southbank 8/11、Parramatta 5/5；合计 **30 个房型卡、38 个标记数量**。没有逐个房号核验，38 不作为唯一房源数。初版探针误用了详情页选择器，输出空集合；已修复，并以原始 HTML 离线复算，原始结果保留，不把解析错误说成网站没有数据。

Novus 列表首响应发现 **8 个唯一挂牌 URL**，存在更多结果的分页入口；没有执行翻页。这只是已见入口数，不是全平台库存，也不证明能收齐 100 条。

两套 simulation projection 使用 `DEMO-` reference、`draft/private`，币种 `AUD` 明确为演示假设；UniLodge 的车位 0 也明确标为模拟字段，原始值仍为 null。不替真实房源伪造可租状态或维修历史。

## 7. 哪些数据需要真实获取

| 数据 | 处理策略 | 不能声称什么 |
|---|---|---|
| 户型图、室内照片、实际文件格式与清晰度 | 优先取得合法真实素材；保留来源、实体关联、尺寸、hash、审核结果 | 生成图片不能替代真实采集质量或图文一致性验证 |
| 视频及连续空间证据 | 优先自有/获授权视频；确认实体关联、MIME、时长、文件完整性 | 楼盘宣传片、VR 链接不等于巡检视频 |
| 价格、房型、面积、报价条件 | 作为真实采集适配基准，未知保留 null | 不混合按床/按人/整套价格，不把房间面积当整套面积 |
| 业务账号、任务、派单状态、内部 reference、流程时间 | 可做隔离测试数据，逐字段/记录标 synthetic | 不能宣称真实入住率、真实 SLA 或维修效率 |
| 真实维修附件、缺陷标注、维修与房源关联 | 通过物业/承包商授权脱敏导出或有许可的标注集另行获取 | 不能给营销图片自动赋予缺陷真值或安全结论 |

## 8. 后续执行与停止条件

1. **准入确认。** 对 UniLodge、Novus 分别确认固定页面读取、字段暂存、原图保存、私有展示、第三方处理和删除要求；未获相应用途许可不进入扩采/发布。优先询问是否能提供许可的数据导出或 feed，而不是只问“能不能爬”。
2. **验证代表性。** 获准后先各取约 10 个不同房型/单元，跨 studio/1卧/2卧/合租，区分楼盘、房型、单元、报价、资产。共享图库只计一次，不按房号重复下载充量。
3. **验证可采规模。** 遍历获准的公开分页或官方导出，按 source+listing_id 去重；分别报告地点数、房型数、单元数、有效报价数、合格媒体单元数。达到至少 100 个独立单元才宣布普通公寓规模目标达成；学生床位/房型不冒充单元。
4. **结构验收。** 逐条检查新增必填字段、面积与报价口径、媒体验证、来源追溯；任何准入失败/关联不明进入隔离队列。媒体及字段覆盖率以全部尝试的目标记录为分母，同时公开失败原因，不能只统计成功样本。
5. **受控演示导入。** 先补独立人工审核，再走测试数据库导入、外键/约束、房源详情展示及删除回滚验证。新建模拟主体，绝不覆盖生产房源。当前两份 JSON 不是业务 API 请求契约。
6. **视频与住宅类型扩展。** 视频独立验收；后续普通住宅另选获准中介 feed/平台 API，覆盖联排、独栋、旧房。不能靠重复同一楼盘一百套代替住宅类型多样性。

停止条件：访问要求登录/验证码、403/429、条款禁止当前用途、范围超过许可、分页结构变化、字段匹配错误、媒体内容与房型不符。不得通过代理轮换、隐蔽端点或账户访问规避。

## 9. 产物与复验

本地证据目录（Git 忽略，不是公开分发包）：

- `data/collection-pilot/flagstaff-20260929-v1`：UniLodge HTML、房型与报价。
- `data/collection-pilot/source-fit-20260929`：4 个 HOME 索引、UniLodge 索引和第一批 3 张图片。
- `data/collection-pilot/novus-20260929`：Novus 条款、索引、详情 HTML 与标准化样例。
- `data/collection-pilot/multimodal-fit-20260929`：补充的 6 张原始图片及抓取记录。
- `data/collection-pilot/source-fit-analysis-20260929`：`unilodge-sample.json`、`novus-sample.json`、`validation.json`、输入输出 hash 清单。

代码：[固定页面探针](../../scripts/data_collection/source_fit_probe.py)、[Novus 解析](../../scripts/data_collection/novus_collect.py)、[媒体补采清单](../../scripts/data_collection/multimodal_probe.py)、[结构分析](../../scripts/data_analysis/source_fit.py)、[按内容 hash 绑定的助手审核](../../scripts/data_analysis/source_fit_reviews.json)。

```powershell
python -m unittest discover -s scripts/data_collection -p "test_*.py"
python -m unittest discover -s scripts/data_analysis -p "test_*.py"
python -X utf8 scripts/data_analysis/source_fit.py --output data/collection-pilot/source-fit-replay
```

测试不访问网络，使用自造 HTML 和测试图片。分析读取冻结快照，不再请求网站，输出目录必须不存在。本轮采集测试 30 项、分析测试 22 项通过。校验器覆盖样例涉及的字段、数值精度、关键新增车位约束及媒体门槛；不替代完整 PostgreSQL 集成测试、外键/唯一性冲突测试或服务层授权验证。

已重复运行至 `source-fit-replay-20260929`：两份样例、校验报告和 manifest 共 4 个 JSON 的 SHA-256 均与首次运行一致。报告中的本地代码链接均检查存在；`git diff --check` 无空白错误。未执行数据库导入、网页发布或超过 100 条的扩采。

最终选择：**UniLodge 用于学生房型与合租场景，Novus 用于具体普通公寓单元与清晰多模态样例。HOME 保留为已有对照来源，不再默认作为唯一主来源。** 扩采的下一关是用途授权和可采库存验证，而不是增加图片数量。
