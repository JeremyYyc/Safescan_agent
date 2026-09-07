# HARASSMENT：举报直属主管

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-HARASSMENT-QA-01 举报直属主管

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: HARASSMENT
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-EMP-004"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 被投诉的人就是我的直属主管，我必须先经过他才能举报吗？材料不完整会不会不受理？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 涉及管理者可直接向上一级、HR 或合规报告，选择安全可信渠道。 | required | (SC-EMP-004 §6.1) |
| C2 | 信息不完整不影响受理，匿名也受理，但可能影响核实，应尽量提供时间地点人员行为等信息。 | required | (SC-EMP-004 §6.2) |

**forbidden_claims**

- 不得编造本轮证据没有提供的数字、个人记录、版本或联系方式。
- 不得将模拟内部政策当作已核验的现行法律。
- 不得引用未交给模型的文档或不支持结论的条款。
- 不得声称已执行申请、审批、付款或系统修改。
- 不得要求先取得被举报主管许可或承诺匿名必能查实。

**insufficient_evidence_behavior**

仅回答实际证据支持的部分并明确具体缺口，必要时转主管/资料维护人；完整问答缺少必答事实仍不通过。

**pass_criteria**

- 所有 required 事实被正确回答且至少一个完整证据选项实际进入模型上下文。
- 所有关键结论引用真实、适用、获授权的证据；禁止项一票否决。
- preferred_sources 未命中不单独判业务问答失败；新等价证据记 needs_review 后人工复核。

**evidence_review**

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-004"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-004 §6.1 · 6.1 报告渠道</summary>

6.1 **报告渠道。** 员工可通过以下任一渠道报告：直属主管或上一级主管；人力资源部；合规部门或法务；以及由独立第三方运营的匿名举报热线与举报邮箱。员工可选择其感到安全与信任的渠道。对涉及管理者的举报，应直接报告至上一级主管、人力资源部或合规部门，以避免利益冲突。

</details>

<details><summary>SC-EMP-004 §6.2 · 6.2 报告内容的要素</summary>

6.2 **报告内容的要素。** 报告应尽量说明：涉及人员、事件发生的时间地点、具体行为、是否有证人、是否已向他人反映、以及对报Gào人的影响。信息不完整不影响报告的受理，公司会视需要补充核实；匿名举报同样会被受理，但可能因信息不足而影响后续核实。

</details>

## TC-V2-HARASSMENT-LOOKUP-01 举报直属主管：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: HARASSMENT
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-EMP-004", "clause": "6.1", "anchor": "6.1 报告渠道"}]
- **preferred_sources**: ["SC-EMP-004"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-EMP-004 第 6.1 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 涉及管理者可直接向上一级、HR 或合规报告，选择安全可信渠道。 | required | (SC-EMP-004 §6.1) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-004"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-004 §6.1 · 6.1 报告渠道</summary>

6.1 **报告渠道。** 员工可通过以下任一渠道报告：直属主管或上一级主管；人力资源部；合规部门或法务；以及由独立第三方运营的匿名举报热线与举报邮箱。员工可选择其感到安全与信任的渠道。对涉及管理者的举报，应直接报告至上一级主管、人力资源部或合规部门，以避免利益冲突。

</details>

