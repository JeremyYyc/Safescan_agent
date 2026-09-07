# VISITOR：访客临时门卡

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-VISITOR-QA-01 访客临时门卡

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: VISITOR
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-SOP-011"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 访客说是住户朋友，我可以直接给他一张住户门卡吗？访客卡要怎样发放和回收？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 应登记访客和被访信息、确认住户在住并经住户确认，再发限时卡。 | required | (SC-SOP-011 §6.2) |
| C2 | 访客卡限有效时段及公共区/被访区域，不得给住户房卡权限；离场收回登记，超时升级 Duty Manager。 | required | (SC-SOP-011 §6.2) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-SOP-011"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-SOP-011 §6.2 · 6.2 步骤二：访客卡发放</summary>

6.2 **步骤二：访客卡发放。** ①登记访客姓名、证件、被访住户、到访时间并确认被访住户在住；②经被访住户确认；③发放限时访客卡并注明有效时段与允许进入范围；④告知访客禁止转借、须随身携带、离场时归还；⑤离场时收回并登记，超时未离场的升级 Duty Manager。注意：访客卡权限应严格为"限定公共区+被访区域"，不得赋予其住户房卡权限，访客不得在无人陪同情况下进入高权限区域。

</details>

## TC-V2-VISITOR-LOOKUP-01 访客临时门卡：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: VISITOR
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-SOP-011", "clause": "6.2", "anchor": "6.2 步骤二：访客卡发放"}]
- **preferred_sources**: ["SC-SOP-011"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-SOP-011 第 6.2 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 应登记访客和被访信息、确认住户在住并经住户确认，再发限时卡。 | required | (SC-SOP-011 §6.2) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-SOP-011"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-SOP-011 §6.2 · 6.2 步骤二：访客卡发放</summary>

6.2 **步骤二：访客卡发放。** ①登记访客姓名、证件、被访住户、到访时间并确认被访住户在住；②经被访住户确认；③发放限时访客卡并注明有效时段与允许进入范围；④告知访客禁止转借、须随身携带、离场时归还；⑤离场时收回并登记，超时未离场的升级 Duty Manager。注意：访客卡权限应严格为"限定公共区+被访区域"，不得赋予其住户房卡权限，访客不得在无人陪同情况下进入高权限区域。

</details>

