# LEAVE：普通休假与紧急请假

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-LEAVE-QA-01 普通休假与紧急请假

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: LEAVE
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-EMP-008"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 普通年假怎么申请？遇到紧急照护来不及提前申请该怎么办？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 一般休假尽量提前通过系统或书面申请，写明类型、日期、时长与原因，由直属上级或站点主管审批。 | required | (SC-EMP-008 §3.2) |
| C2 | 紧急情况尽快通知当班负责人并按规定补办；审批要考虑排班、运营、最低人手及公平。 | required | (SC-EMP-008 §3.2) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-008"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-008 §3.2 · 3.2 申请流程</summary>

3.2 **申请流程。** 一般休假（如年假）应尽量提前通过公司系统或书面提出申请，说明休假类型、起止日期、预计时长与原因，经直属上级或站点主管审批。审批应基于运营需要、排班可行性、最低在岗人数与该员工/同事的公平安排，而非随意拒绝。审批结果应记录并回告员工；因突发情况（如突发事件、紧急照护）临时请假的，员工应尽快通知当班负责人并按规定补办。

</details>

## TC-V2-LEAVE-LOOKUP-01 普通休假与紧急请假：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: LEAVE
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-EMP-008", "clause": "3.2", "anchor": "3.2 申请流程"}]
- **preferred_sources**: ["SC-EMP-008"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-EMP-008 第 3.2 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 一般休假尽量提前通过系统或书面申请，写明类型、日期、时长与原因，由直属上级或站点主管审批。 | required | (SC-EMP-008 §3.2) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-008"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-008 §3.2 · 3.2 申请流程</summary>

3.2 **申请流程。** 一般休假（如年假）应尽量提前通过公司系统或书面提出申请，说明休假类型、起止日期、预计时长与原因，经直属上级或站点主管审批。审批应基于运营需要、排班可行性、最低在岗人数与该员工/同事的公平安排，而非随意拒绝。审批结果应记录并回告员工；因突发情况（如突发事件、紧急照护）临时请假的，员工应尽快通知当班负责人并按规定补办。

</details>

