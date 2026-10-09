# UniLodge Flagstaff 小样本采集

日期：2026-09-29。状态：公开页面基础数据与媒体链接已采集；媒体文件未下载，未发布。

## 范围与结果

固定采集楼盘页、条款页和 3 个房型分类页，共 5 个页面；另检查两个主机的 robots.txt。采集运行共 7 次请求，全部返回 200，无重试。此请求数不包含运行前的浏览研究和结构检查。

| 房型 | 面积及作用域 | 页面周报价 | 租期报价条数 | 房型图库链接 |
|---|---|---|---:|---:|
| Studio Standard | Studio 13㎡ | $509 / $529 / $539 | 3 | 6 |
| Studio Terrace | Studio 13㎡ | $555 / $575 | 2 | 4 |
| Studio Queen | Studio 16㎡ | 无可选租期报价 | 0 | 2 |
| 2 Bedroom Apartment | 每卧室 12㎡，非整套面积 | 无可选租期报价 | 0 | 2 |
| 4 Bedroom Apartment | 每卧室 8㎡，非整套面积 | 每人 $429 / $449 | 2 | 3 |

合计 5 个房型、7 条报价、17 条不同房型图库 URL、4 条不同 VR 链接。楼盘页另识别出 6 个户型图候选 URL，与房型图库可能内容重复，不能相加成唯一图片数。图库中包含图纸，不能把 17 条全部算为室内照片。

报价按原页面美元符号记录，当前解析未找到明确币种代码，标准化 currency 保留 null，不能声称已完成全部报价口径确认。Standard 的前三个价格依次对应 2027 第一学期全年、半年，以及十二月至一月暑期；Terrace 和四卧各对应前两种租期。Studio 未从“住一人”自动推定按人或按套计价。

表单默认起止日期已提取并标注为页面默认值，不代表确认合同或实时库存。未提交申请、选择日期或访问住户账户。来源明确提示展示照片可能不对应实际房号。

## 验证与修复

- 首版只查询 img 标签，漏掉 CSS 背景图库；改用 tinycss2 解析房型分区内的 background-image，链接数由 0 修复到 17。
- Studio Queen 使用与其他房型不同的面积句式，修复后面积字段由 4/5 提升到 5/5；始终保留面积作用域。
- 保存网页哈希、采集时间、请求响应记录、解析器哈希及结果哈希；解析阶段先核验原始快照。
- 23 项采集器测试通过，其中 6 项针对 Flagstaff，覆盖房型隔离、按人报价、缺价、结构变化、CSS 图库和链接去重。
- 同一快照离线复算与保存结果一致。未将链接存在当作图片清晰、VR 可播放或素材使用获准。

## 访问和使用边界

主站 robots 未禁止这些路径；预订子站的公开 categoryInfo 页面不在本次检查到的禁用路径内。账户、预订流程等路径存在限制，本工具不访问。robots 不是开放素材许可证，rights_status 仍为 unknown。

本轮是有限公开 HTML 研究快照，不是扩量素材下载或授权数据发布。原始 HTML 和结构化结果留在 Git 忽略的本地目录。此前流程中的“权限未明不扩大媒体下载或公开使用”仍适用。

## 下一步

先确认媒体保存和使用范围，再对 Standard、Terrace、四卧各挑选一张图纸及至少两张室内候选图验证。优先检查图纸是否被裁切、是否能看清尺寸，以及同一房型图库中哪些是图纸、室内或宣传内容。

Queen 与图库中的 Deluxe Queen 名称不同，不能直接合并。没有报价的房型保留缺失，不从其他房型补价。当前暂不接入旧 9 房型基线，也不宣布新增完整合格样本。

## 入口与复现

- [楼盘与户型图入口](https://www.unilodge.com.au/student-accommodation-melbourne/melbourne-flagstaff)
- [Studio 详情](https://www.reserve.unilodge.com.au/categoryInfo.html?category=488)
- [两卧详情](https://www.reserve.unilodge.com.au/categoryInfo.html?category=489)
- [四卧详情](https://www.reserve.unilodge.com.au/categoryInfo.html?category=490)
- [本地房型、报价与图库链接](../../data/collection-pilot/flagstaff-20260929-v1/room_types.json)
- [本地图纸候选清单](../../data/collection-pilot/flagstaff-20260929-v1/media_candidates.json)
- [采集脚本](../../scripts/data_collection/flagstaff_collect.py)

```powershell
python -m pip install -r scripts/data_collection/requirements.txt
python -X utf8 scripts/data_collection/flagstaff_collect.py --process data/collection-pilot/flagstaff-20260929-v1
python -X utf8 -m unittest discover -s scripts/data_collection -p "test_*.py"
```

--process 只读取本地快照，不联网，会重建派生结果；--output 用于采集并要求新目录。此采集器只有固定页面范围，没有媒体下载和表单提交功能。本地数据链接在不含快照的 Git 克隆中不可用。
