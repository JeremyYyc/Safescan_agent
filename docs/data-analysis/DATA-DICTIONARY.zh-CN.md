# 离线基线字段与指标字典

版本：`housing-baseline-v2`。本文描述当前实现，不将总体方案中的完整目标模型标成已落地。

## 实体与字段

JSON 是完整明细；SQLite 的 `samples/offers/units/assets/checks` 保留主键、关联键及 JSON `payload`，用于离线查询与一致性验证，不是生产业务表。

| 实体 | 粒度与键 | 主要字段及约束 |
|---|---|---|
| samples | 一来源房型；id 唯一 | source_id、property_id、name、location、source_url、retrieved_at；record_type 固定 room_type |
| samples 参数 | 房型属性，可空 | bedrooms、bathrooms、area_sqm；不从名称猜测，不把房号面积复制为房型面积 |
| offers | 一报价；id 唯一，sample_id 外键 | amount 为非负有限十进制字符串；currency、period、basis、lease_condition 可空；unit_id 可空 |
| offers 口径 | 一条报价的使用条件 | basis 仅接受 person/room/unit；历史记录未确认则 null；lease_condition 当前均 null |
| units | 一具体房号；id 唯一，sample_id 外键 | unit_number_raw、area_sqm；面积单位平方米，area_scope 当前 unknown |
| assets | 一来源媒体记录；id 唯一 | sample_id 可空；url、kind、local_path、content_key、integrity；媒体记录数不等于唯一内容数 |
| assets 审核 | 与内容哈希绑定 | category、association、usable、review_status；助手建议不能设置 human_approved=true |
| checks | 一房型检查；sample_id 唯一外键 | core_fields、reasons、quality_pass、approved_for_use、interior_count、floorplan_count、offer_count |
| issues | 一异常记录 | id、rule、detail；文件校验失败保留异常，不能静默变成正常图片 |
| source_registry | 一来源 | rights_status 当前 unknown、approved_scopes 为空；本工具不授予权限 |
| manifest | 一次执行 | cohort_id、版本、UTC时间、Git状态、输入/输出及代码配置哈希；不是发布许可 |

`source_file` 定位原 JSON；原始报价和来源链接保留在报价明细，输入快照不覆盖。位置修复另记 `location_basis`。基础字段缺失以 null 表示；报价记录的 `missing_reason` 说明历史记录需回查，不能据此断言网站未提供。细粒度逐字段缺失原因、完整资产关联表及人工审核导入仍待补齐。

## 计算口径

| 指标 | 当前公式 | 本轮例子 |
|---|---|---|
| identity_completeness | 六个身份字段已填项 / 房型数×6 | 54/54；字段为 id、name、property_id、location、source_url、retrieved_at |
| room_parameter_completeness | 卧室数、卫浴数、面积非空项 / 房型数×3 | 5/27；仅测填充，不等于面积口径已核准 |
| offer_completeness | 金额、币种、周期、计价基础、租期五项明确的报价 / 报价数 | 0/8 |
| image_integrity | 通过解码、尺寸和哈希校验的图片记录 / 本地图片记录 | 27/27 |
| exact_image_duplicate_rate | 已验证图片记录数减唯一内容数 / 已验证图片记录数 | (27-26)/27；失败图片另列，不当重复 |
| quality_pass_rate | 所有当前质量检查通过的房型 / 固定队列房型 | 0/9；该历史队列均已执行自动检查，但人工审核待完成 |
| verified_floorplan_coverage | 有人工认可、可读且匹配图纸的房型 / 已评估房型 | 0/9；不是网页户型图链接存在率 |
| verified_interior_coverage | 有至少两张去重、人工认可室内图的房型 / 已评估房型 | 0/9 |
| use_admission_rate | 获准使用的质量合格房型 / 质量合格房型 | 0/0，显示 N/A |
| home_assistant_suggested_core_media | HOME 去重后初步可用室内图或图纸 / HOME 去重图片 | 4/13；仅助手分类建议 |

所有比率保存 numerator、denominator、value；零分母的 value 为 null，并附原因。`unknown` 不视为已填；数字零不是缺失值。人工关联准确率、请求成功率和样本成本缺少证据时显示 N/A。

本轮只能反映两个已保存来源的便利样本。没有完整历史请求日志，不实现或推断页面获取漏斗；视频、VR 可用覆盖和市场价格分析也不从现有链接数推导。

## 复验

两次运行使用相同 cohort 配置、分类建议和原始快照，写入不同新目录。`verify_run.py` 校验输入及输出哈希、SQLite 数量和外键，并比较 JSON 与 Markdown。运行时间和 manifest 本身不要求逐字相同。具体命令见 [脚本说明](../../scripts/data_analysis/README.md)。
