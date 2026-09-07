# PERFORMANCE：绩效与纪律区分

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-PERFORMANCE-QA-01 绩效与纪律区分

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: PERFORMANCE
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-EMP-005"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 员工只是业务能力未达标，没有发现违规，能不能直接按违纪处理？改进计划应写哪些内容？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 能力表现问题与行为合规问题应区分，绩效以改进支持为导向，不能把单纯未达标直接等同违纪。 | required | (SC-EMP-005 §2.1) |
| C2 | 未达标时主管会同 HR 制定书面 PIP，明确目标、衡量、支持培训、评估时点和未改进后果，并给予合理时间。 | required | (SC-EMP-005 §3.4) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-005"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-005 §2.1 · 2.1 区分</summary>

2.1 **区分。** 绩效管理通常用于处理"能力、表现与结果"问题（如未达标、技能不足、工作质量不佳），以改进与支持为导向；纪律处分通常用于处理"行为与合规"问题（如违反政策、不诚信、安全违规、骚扰歧视），以矫正与问责为导向。两者可能交织，但性质不同，处理方式也不同。

</details>

<details><summary>SC-EMP-005 §3.4 · 3.4 步骤四：改进计划（PIP）</summary>

3.4 **步骤四：改进计划（PIP）。** 若评估表明未达标，主管应会同人力资源部制定书面的绩效改进计划（Performance Improvement Plan），明确：具体改进目标、衡量方式、支持与培训、评估时点，以及未改进的后果。PIP 的期限应合理（如数个工作周至数月），并给员工足够时间与支持。PIP 目标应具体可追踪，员工有权了解进展。

</details>

## TC-V2-PERFORMANCE-LOOKUP-01 绩效与纪律区分：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: PERFORMANCE
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-EMP-005", "clause": "2.1", "anchor": "2.1 区分"}]
- **preferred_sources**: ["SC-EMP-005"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-EMP-005 第 2.1 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 能力表现问题与行为合规问题应区分，绩效以改进支持为导向，不能把单纯未达标直接等同违纪。 | required | (SC-EMP-005 §2.1) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-005"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-005 §2.1 · 2.1 区分</summary>

2.1 **区分。** 绩效管理通常用于处理"能力、表现与结果"问题（如未达标、技能不足、工作质量不佳），以改进与支持为导向；纪律处分通常用于处理"行为与合规"问题（如违反政策、不诚信、安全违规、骚扰歧视），以矫正与问责为导向。两者可能交织，但性质不同，处理方式也不同。

</details>

