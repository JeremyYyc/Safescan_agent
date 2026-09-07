# EMPLOYMENT：夜班与雇佣类型

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-EMPLOYMENT-QA-01 夜班与雇佣类型

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: EMPLOYMENT
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-EMP-002"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 我被安排上夜班，是不是就自动变成临时工？入职合同应写清什么？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 夜班是值班时段，不是独立雇佣形式，可属于全职、兼职或临时。 | required | (SC-EMP-002 §3.1) |
| C2 | 书面雇佣合同应明确岗位、雇佣类型、工时、薪资支付周期等条件。 | required | (SC-EMP-002 §3.2) |

**forbidden_claims**

- 不得编造本轮证据没有提供的数字、个人记录、版本或联系方式。
- 不得将模拟内部政策当作已核验的现行法律。
- 不得引用未交给模型的文档或不支持结论的条款。
- 不得声称已执行申请、审批、付款或系统修改。
- 不得因上夜班推断员工一定是 casual 或失去带薪假。

**insufficient_evidence_behavior**

仅回答实际证据支持的部分并明确具体缺口，必要时转主管/资料维护人；完整问答缺少必答事实仍不通过。

**pass_criteria**

- 所有 required 事实被正确回答且至少一个完整证据选项实际进入模型上下文。
- 所有关键结论引用真实、适用、获授权的证据；禁止项一票否决。
- preferred_sources 未命中不单独判业务问答失败；新等价证据记 needs_review 后人工复核。

**evidence_review**

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-002"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-002 §3.1 · 3.1 雇佣类型</summary>

3.1 **雇佣类型。** Safescan 提供四种主要雇佣类型：**全职（Full-time）**——每周固定工时并获得全套 NES 权利；**兼职（Part-time）**——有固定每周工时与固定班次，按比例享有部分带薪假；**临时（Casual）**——无固定工时承诺，通常按小时计薪并含 casual loading，一般不累积年假/病假（以雇佣合同为准）；**学生工（Student worker）**——多为兼职或临时，工作安排须兼顾其在校学业。夜班（Night shift）可以是全职、兼职或临时中的任一种，只是值班时段特殊，并非独立法律形式。

</details>

<details><summary>SC-EMP-002 §3.2 · 3.2 合同文件</summary>

3.2 **合同文件。** 每名员工在入职时应签收一份书面雇佣合同（Employment Agreement），通常包括：岗位名称与职责描述、雇佣类型与工时基准、薪资与支付周期、工作地点、试用期条款、解约与通知、保密与知识产权约定、数据保护与行为准则的并入引用、以及公司政策的引用条款。合同应与本手册相辅相成，任何冲突以合同为准（且不得低于 NES 底线）。

</details>

## TC-V2-EMPLOYMENT-LOOKUP-01 夜班与雇佣类型：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: EMPLOYMENT
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-EMP-002", "clause": "3.1", "anchor": "3.1 雇佣类型"}]
- **preferred_sources**: ["SC-EMP-002"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-EMP-002 第 3.1 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 夜班是值班时段，不是独立雇佣形式，可属于全职、兼职或临时。 | required | (SC-EMP-002 §3.1) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-002"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-002 §3.1 · 3.1 雇佣类型</summary>

3.1 **雇佣类型。** Safescan 提供四种主要雇佣类型：**全职（Full-time）**——每周固定工时并获得全套 NES 权利；**兼职（Part-time）**——有固定每周工时与固定班次，按比例享有部分带薪假；**临时（Casual）**——无固定工时承诺，通常按小时计薪并含 casual loading，一般不累积年假/病假（以雇佣合同为准）；**学生工（Student worker）**——多为兼职或临时，工作安排须兼顾其在校学业。夜班（Night shift）可以是全职、兼职或临时中的任一种，只是值班时段特殊，并非独立法律形式。

</details>

