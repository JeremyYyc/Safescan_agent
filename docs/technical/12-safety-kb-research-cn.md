# 中国大陆 Safety KB 首批资源调研

**调研日期**：2026-08-27
**用途**：为 MVP 的 Safety KB v1 建立候选来源池。以下资源用于家庭安全知识和风险解释，不等同于法律意见或合规判定。

## 1. 首批推荐来源

| 优先级 | 来源 | 推荐主题 | 入库建议 |
|---|---|---|---|
| Tier 1 | [中国消防/国家消防救援局家庭科普](https://www.119.gov.cn/kp/hzyf/jt/2024/45745.shtml) | 家庭防火、燃气泄漏、电气火灾、逃生 | 作为家庭消防主干来源 |
| Tier 1 | [中国消防：家庭消防安全攻略](https://www.119.gov.cn/site1/kp/hzyf/jt/2022/1205.shtml) | 烹饪、可燃物、电路、吸烟 | 按“风险/原因/建议”切分 |
| Tier 1 | [中国消防：家庭防火知识](https://www.119.gov.cn/kp/hzyf/jt/2022/1295.shtml) | 灭火器、逃生、燃气泄漏、线路老化、超负荷用电 | 适合 Recommendation Agent，操作措辞需人工复核 |
| Tier 1 | [中国消防：三清三关](https://gz.119.gov.cn/xfkp/xfcs/202201/t20220104_72197965.html) | 走道、阳台、厨房、电源、气源、门窗 | 适合家庭环境风险解释 |
| Tier 1 | [应急管理部电气火灾防控资料](https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202308/W020230821686451916954.pdf) | 城镇民用建筑电气火灾风险 | 作为专业补充资料 |
| Tier 1 | [市场监管总局：家用电器安全使用年限](https://www.samr.gov.cn/xw/sj/art/2025/art_c99280da32a741a7b2143e383f4fad99.html) | 老旧家电、使用年限、超期风险 | 后续 Device/家电主题，记录实施日期 |
| Tier 1 | [全国标准信息公共服务平台](https://std.samr.gov.cn/) | 国家标准检索入口 | 只在确认现行状态和适用范围后入库 |

## 2. 采集与审核规则

1. 优先采集政府官网、消防救援机构、应急管理部门和市场监管部门内容。
2. 不抓取论坛、营销文章、未经审核博客作为主干知识。
3. 保存原始 URL、页面标题、发布时间、抓取时间、来源机构、语言和授权信息。
4. 来源先进入 `draft`，人工审核后才变为 `published`；内容修订时创建新版本，不覆盖旧版本。
5. 保留原始中文术语，如“超负荷用电”“燃气泄漏”“消防通道”；向量索引只作为关键词检索的补充。

## 3. MVP 建议首批主题

```text
家庭防火、厨房明火与可燃物、电气线路与超负荷、燃气泄漏、消防通道与逃生、家用电器安全使用
```

暂不纳入：需要工程测量才能判断的结构结论、没有明确适用范围的法规解释、医疗诊断和强制整改结论。

## 4. 入库字段示例

```json
{
  "kb_type": "safety",
  "locale": "zh-CN",
  "source_type": "government_guidance",
  "trust_tier": 1,
  "official_url": "https://www.119.gov.cn/...",
  "jurisdiction": {"country": "CN", "scope": "mainland"},
  "status": "draft",
  "reviewed_at": null
}
```

正式代码实现前必须替换占位 URL，并增加 URL 可访问性与 metadata schema 校验。
