# RATECARD：房型描述与实际报价

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-RATECARD-QA-01 房型描述与实际报价

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: RATECARD
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-PRD-002"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 目录写了典型面积和全包设施，我能直接保证每套都一样、所有费用都免费吗？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 面积床型为典型配置，具体以楼宇平面和协议附件为准，报价需明确楼宇房号。 | required | (SC-PRD-002 §2.2) |
| C2 | 免费/全包说法要与协议附件一致，不能作一切费用全免的绝对承诺。 | required | (SC-PRD-002 §8.7) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-PRD-002"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-PRD-002 §2.2 · 2.2</summary>

2.2 上述面积与床型为典型配置，具体以各楼宇平面与协议附件为准。销售与预订团队在报价时应注明楼宇代号（如 SYD-PA、BNE-RV）与具体房号，避免按"房型名"而非"实际房号"混淆报价。

</details>

<details><summary>SC-PRD-002 §8.7 · 8.7</summary>

8.7 涉及"免费""全包"等表述时，须与协议附件一致，不得作"一切费用全免"之类的绝对化承诺；若某州对租房广告收费披露有额外要求，以该州官方指引为准。

</details>

## TC-V2-RATECARD-LOOKUP-01 房型描述与实际报价：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: RATECARD
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-PRD-002", "clause": "2.2", "anchor": "2.2"}]
- **preferred_sources**: ["SC-PRD-002"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-PRD-002 第 2.2 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 面积床型为典型配置，具体以楼宇平面和协议附件为准，报价需明确楼宇房号。 | required | (SC-PRD-002 §2.2) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-PRD-002"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-PRD-002 §2.2 · 2.2</summary>

2.2 上述面积与床型为典型配置，具体以各楼宇平面与协议附件为准。销售与预订团队在报价时应注明楼宇代号（如 SYD-PA、BNE-RV）与具体房号，避免按"房型名"而非"实际房号"混淆报价。

</details>

