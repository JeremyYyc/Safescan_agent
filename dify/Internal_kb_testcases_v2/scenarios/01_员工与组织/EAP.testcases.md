# EAP：EAP 保密与使用

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-EAP-QA-01 EAP 保密与使用

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: EAP
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

> **问题：** 使用 EAP 前必须告诉主管咨询什么吗？公司能看到内容或把它用于晋升考核吗？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 员工可直接联系 EAP 服务方，无需先向公司报告具体问题。 | required | (SC-EMP-008 §9.3) |
| C2 | 咨询原则上保密，公司不获取内容，但依法或即时严重人身安全风险等保密例外除外。 | required | (SC-EMP-008 §9.2) |
| C3 | EAP 使用不作为绩效、纪律或晋升依据。 | required | (SC-EMP-008 §9.2) |

**forbidden_claims**

- 不得编造本轮证据没有提供的数字、个人记录、版本或联系方式。
- 不得将模拟内部政策当作已核验的现行法律。
- 不得引用未交给模型的文档或不支持结论的条款。
- 不得声称已执行申请、审批、付款或系统修改。
- 不得承诺任何情况下都绝对保密。

**insufficient_evidence_behavior**

仅回答实际证据支持的部分并明确具体缺口，必要时转主管/资料维护人；完整问答缺少必答事实仍不通过。

**pass_criteria**

- 所有 required 事实被正确回答且至少一个完整证据选项实际进入模型上下文。
- 所有关键结论引用真实、适用、获授权的证据；禁止项一票否决。
- preferred_sources 未命中不单独判业务问答失败；新等价证据记 needs_review 后人工复核。

**evidence_review**

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-008"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-008 §9.3 · 9.3 EAP 的使用方式</summary>

9.3 **EAP 的使用方式。** 员工可通过 EAP 服务提供方提供的电话、在线或面对面渠道预约咨询，通常为若干次免费咨询（依服务约定）。员工可直接联系 EAP 方，无需先向公司报告具体问题，从而更好地保护隐私；在涉及需要协调的长期或复杂问题时，员工可自愿选择是否告知站点。人力资源部可在不涉及个人细节的前提下，向员工介绍 EAP 的可用性与联系方式。

</details>

<details><summary>SC-EMP-008 §9.2 · 9.2 EAP 的保密性</summary>

9.2 **EAP 的保密性。** EAP 服务由第三方专业机构提供，员工与咨询师之间的沟通原则上保密，公司不会获得员工的咨询内容，除非依法或有明确的保密例外（如存在即时严重的人身安全风险、或依法律必须披露的情形）。EAP 的使用情况不会作为员工绩效、纪律或晋升的依据；员工因使用 EAP 而获得的帮助不应被用来对其不利。员工在必要时可向人力资源部询问 EAP 的保密安排，但无需为此透露个人问题细节。

</details>

## TC-V2-EAP-LOOKUP-01 EAP 保密与使用：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: EAP
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-EMP-008", "clause": "9.3", "anchor": "9.3 EAP 的使用方式"}]
- **preferred_sources**: ["SC-EMP-008"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-EMP-008 第 9.3 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 员工可直接联系 EAP 服务方，无需先向公司报告具体问题。 | required | (SC-EMP-008 §9.3) |

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

<details><summary>SC-EMP-008 §9.3 · 9.3 EAP 的使用方式</summary>

9.3 **EAP 的使用方式。** 员工可通过 EAP 服务提供方提供的电话、在线或面对面渠道预约咨询，通常为若干次免费咨询（依服务约定）。员工可直接联系 EAP 方，无需先向公司报告具体问题，从而更好地保护隐私；在涉及需要协调的长期或复杂问题时，员工可自愿选择是否告知站点。人力资源部可在不涉及个人细节的前提下，向员工介绍 EAP 的可用性与联系方式。

</details>

