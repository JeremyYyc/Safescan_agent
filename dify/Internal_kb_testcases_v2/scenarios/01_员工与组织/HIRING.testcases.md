# HIRING：背景核验最小必要

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-HIRING-QA-01 背景核验最小必要

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: HIRING
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-EMP-009"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 所有岗位都统一查犯罪记录最省事吗？应如何限定核验范围和结果用途？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 核验范围须与岗位相关且相称，不对所有岗位过度核验。 | required | (SC-EMP-009 §6.1) |
| C2 | 犯罪记录核验须有岗位需要及合法要求并取得授权，只作岗位相关评估，不因记录一概拒绝。 | required | (SC-EMP-009 §6.5) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-009"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-009 §6.1 · 6.1 核验的范围与必要性</summary>

6.1 **核验的范围与必要性。** 背景核验旨在确认候选人身份、工作权利，并视岗位评估其适任性，降低用人风险。核验的范围应与岗位相关且相称，不应对所有岗位一律施加过度核验，导致对当事人不必要的信息收集。涉及儿童工作核验、犯罪记录检查等敏感核验的，应对应岗位是否确实涉及相关职责（如接触 U18 住户、值守涉及未成年人安全、驾驶或敏感设施）而设定。

</details>

<details><summary>SC-EMP-009 §6.5 · 6.5 犯罪记录核验</summary>

6.5 **犯罪记录核验。** 犯罪记录核验适用于岗位确有需要、且符合相关法律要求的场景（如涉及洗钱、金融、安全、U18 特殊岗位或特定牌照要求）。核验应遵循相关法律（如州法规定的披露与自愿核验程序）并取得候选人授权，结果仅用于与岗位相关的评估。犯罪记录属敏感信息，其处理与保存遵循 SC-EMP-006 的严格保护要求；公司不得在无法律依据或无岗位相关性的情况下任意进行犯罪记录检查，也不得歧视性地因记录而一概拒绝（应结合性质、时间与相关性评估）。

</details>

## TC-V2-HIRING-LOOKUP-01 背景核验最小必要：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: HIRING
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-EMP-009", "clause": "6.1", "anchor": "6.1 核验的范围与必要性"}]
- **preferred_sources**: ["SC-EMP-009"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-EMP-009 第 6.1 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 核验范围须与岗位相关且相称，不对所有岗位过度核验。 | required | (SC-EMP-009 §6.1) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-009"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-009 §6.1 · 6.1 核验的范围与必要性</summary>

6.1 **核验的范围与必要性。** 背景核验旨在确认候选人身份、工作权利，并视岗位评估其适任性，降低用人风险。核验的范围应与岗位相关且相称，不应对所有岗位一律施加过度核验，导致对当事人不必要的信息收集。涉及儿童工作核验、犯罪记录检查等敏感核验的，应对应岗位是否确实涉及相关职责（如接触 U18 住户、值守涉及未成年人安全、驾驶或敏感设施）而设定。

</details>

