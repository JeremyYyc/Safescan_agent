# CONFLICT：亲属供应商利益冲突

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-CONFLICT-QA-01 亲属供应商利益冲突

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: CONFLICT
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-EMP-003"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 亲属的维修公司想参加我负责的采购，即使我觉得能公平评选，也需要申报和回避吗？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 亲属供应商可能构成实际、潜在或感知冲突，不能仅因自认无私就忽略。 | required | (SC-EMP-003 §5.1 AND SC-EMP-003 §5.2) |
| C2 | 应在参与决策前主动书面向主管与 HR 或合规申报，不确定时倾向申报。 | required | (SC-EMP-003 §5.3) |
| C3 | 主管与 HR/合规评估后安排回避或无冲突人员决策，并记录处理。 | required | (SC-EMP-003 §5.4) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-003"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-003 §5.1 · 5.1 利益冲突定义</summary>

5.1 **利益冲突定义。** 利益冲突是指员工的个人利益（自身、亲友或关联方的经济利益、关系或立场）可能或事实上与公司利益冲突的情形，涵盖"实际冲突""潜在冲突"与"感知冲突"三种状态。即便个人无主观私心，只要外界可能合理感知到存在偏向，即应妥善处理，以维护决策的客观与公信。

</details>

<details><summary>SC-EMP-003 §5.2 · 5.2 常见冲突场景</summary>

5.2 **常见冲突场景。** 常见场景包括：员工或其亲属是某供应商、代理或承包商的所有者或受益人；员工参与决定聘用、评估或奖励与自己有私人关系的人员；员工将业务（如维修、清洁、采购）交给自己或亲友经营的公司；员工利用公司信息为个人或亲友谋取便利；员工在可能影响酬金、佣金或合同的决定中存在个人利益。

</details>

<details><summary>SC-EMP-003 §5.3 · 5.3 申报流程</summary>

5.3 **申报流程。** 一旦意识到自己可能处于或即将处于利益冲突，员工应主动、及时、书面申报至主管与人力资源部（或合规部门），说明冲突性质、涉及的个人利益与可能影响。申报应在参与相关决策或以公司名义交易之前进行，而非事后补报。不确定是否构成冲突时，应倾向申报并获书面答复。

</details>

<details><summary>SC-EMP-003 §5.4 · 5.4 申报后的处理</summary>

5.4 **申报后的处理。** 收到申报后，主管与人力资源部/合规应评估冲突程度并作出安排：由该员工回避相关决策、将决策交由无冲突人员处理、或要求员工剥离与其无关的个人利益。涉及重要利益冲突的应予记录并纳入合规台账。回避与处理安排应向员工透明说明。

</details>

## TC-V2-CONFLICT-LOOKUP-01 亲属供应商利益冲突：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: CONFLICT
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-EMP-003", "clause": "5.1", "anchor": "5.1 利益冲突定义"}, {"doc_id": "SC-EMP-003", "clause": "5.2", "anchor": "5.2 常见冲突场景"}]
- **preferred_sources**: ["SC-EMP-003"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-EMP-003 第 5.1 条/节、SC-EMP-003 第 5.2 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 亲属供应商可能构成实际、潜在或感知冲突，不能仅因自认无私就忽略。 | required | (SC-EMP-003 §5.1 AND SC-EMP-003 §5.2) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-003"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-003 §5.1 · 5.1 利益冲突定义</summary>

5.1 **利益冲突定义。** 利益冲突是指员工的个人利益（自身、亲友或关联方的经济利益、关系或立场）可能或事实上与公司利益冲突的情形，涵盖"实际冲突""潜在冲突"与"感知冲突"三种状态。即便个人无主观私心，只要外界可能合理感知到存在偏向，即应妥善处理，以维护决策的客观与公信。

</details>

<details><summary>SC-EMP-003 §5.2 · 5.2 常见冲突场景</summary>

5.2 **常见冲突场景。** 常见场景包括：员工或其亲属是某供应商、代理或承包商的所有者或受益人；员工参与决定聘用、评估或奖励与自己有私人关系的人员；员工将业务（如维修、清洁、采购）交给自己或亲友经营的公司；员工利用公司信息为个人或亲友谋取便利；员工在可能影响酬金、佣金或合同的决定中存在个人利益。

</details>

