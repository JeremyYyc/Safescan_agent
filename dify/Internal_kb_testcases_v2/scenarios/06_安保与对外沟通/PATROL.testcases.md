# PATROL：巡更频次依据

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-PATROL-QA-01 巡更频次依据

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: PATROL
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-SAF-013"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 夜间巡更是不是全国统一规定每小时一次？路线和频次按什么确定？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 路线根据风险与建筑布局设计覆盖关键点，兼顾可操作性和人员安全。 | required | (SC-SAF-013 §6.1) |
| C2 | 频率依据站点风险，是内部服务标准；具体看站点安保配置表，不能编全国固定次数。 | required | (SC-SAF-013 §6.2) |

**forbidden_claims**

- 不得编造本轮证据没有提供的数字、个人记录、版本或联系方式。
- 不得将模拟内部政策当作已核验的现行法律。
- 不得引用未交给模型的文档或不支持结论的条款。
- 不得声称已执行申请、审批、付款或系统修改。

**insufficient_evidence_behavior**

仅回答实际证据支持的部分并明确具体缺口，必要时转主管/资料维护人；完整问答缺少必答事实仍不通过。

**pass_criteria**

- 所有 required 事实被正确回答且至少一个完整证据选项实际进入模型上下文。
- 所有关键结论引用真实、适用、获授权的证据；禁止项一票否决。
- preferred_sources 未命中不单独判业务问答失败；新等价证据记 needs_review 后人工复核。

**evidence_review**

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-SAF-013"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-SAF-013 §6.1 · 6.1 巡更设计</summary>

6.1 **巡更设计**：各站点应根据风险分级与建筑布局设计巡更路线，覆盖出入口、外围、停车场、楼道、设备机房、垃圾房、泳池、屋顶平台等关键点位，并设置巡更点以记录巡查情况。巡更路线应合理、可操作，兼顾巡检重点与保安行动安全；高风险站点可加密巡更并增加夜间与高峰时段巡查。

</details>

<details><summary>SC-SAF-013 §6.2 · 6.2 巡逻频率</summary>

6.2 **巡逻频率**：巡更频率依据站点风险分级设定（此为 Safescan 内部服务标准，非法规要求）：高风险站点建议较高频率巡逻（如每班次多次或不间断），中低风险站点视情况设定期巡逻。夜班时段应结合夜班经理与保安职责安排，确保非营运时段楼宇与外围的持续可视与巡查。具体频率在站点《安保配置表》中明确。

</details>

## TC-V2-PATROL-LOOKUP-01 巡更频次依据：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: PATROL
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-SAF-013", "clause": "6.1", "anchor": "6.1 巡更设计"}]
- **preferred_sources**: ["SC-SAF-013"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-SAF-013 第 6.1 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 路线根据风险与建筑布局设计覆盖关键点，兼顾可操作性和人员安全。 | required | (SC-SAF-013 §6.1) |

**forbidden_claims**

- 不得编造本轮证据没有提供的数字、个人记录、版本或联系方式。
- 不得将模拟内部政策当作已核验的现行法律。
- 不得引用未交给模型的文档或不支持结论的条款。
- 不得声称已执行申请、审批、付款或系统修改。

**insufficient_evidence_behavior**

仅回答实际证据支持的部分并明确具体缺口，必要时转主管/资料维护人；完整问答缺少必答事实仍不通过。

**pass_criteria**

- 所有 required_targets 在固定 Top K 中命中，且支持条款实际传给模型。
- 回答覆盖指定条款的本用例必答事实；其他来源不能替代定位目标；禁止项不出现。

**evidence_review**

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-SAF-013"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-SAF-013 §6.1 · 6.1 巡更设计</summary>

6.1 **巡更设计**：各站点应根据风险分级与建筑布局设计巡更路线，覆盖出入口、外围、停车场、楼道、设备机房、垃圾房、泳池、屋顶平台等关键点位，并设置巡更点以记录巡查情况。巡更路线应合理、可操作，兼顾巡检重点与保安行动安全；高风险站点可加密巡更并增加夜间与高峰时段巡查。

</details>

