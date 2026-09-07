# NIGHT-GENERAL：夜班报备与冲突安全

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-NIGHT-GENERAL-QA-01 夜班报备与冲突安全

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: NIGHT-GENERAL
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-EMP-007"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 单人夜班怎么报备？遇到情绪激动的住户能独自硬处理吗？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 夜班单兵在上下班和关键时间点向指定负责人或系统报备；失联按约定流程核查。 | required | (SC-EMP-007 §6.1) |
| C2 | 处理冲突应保持距离、避免独处，必要时呼叫支援或保安/警方，不单独冒险处理高风险事件。 | required | (SC-EMP-007 §6.5) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-007"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-007 §6.1 · 6.1 双人报备</summary>

6.1 **双人报备。** 夜班与单兵岗位应实行"报备"制度，即值守员工在上班、下班以及关键时间点向指定的值班负责人或系统进行报备，以确认其在岗且安全。报备的方式可为定时打卡、系统签到、与当班调度确认等。若员工未能按时报备且无法联答，站点应按约定的失联处理流程启动核查，防止单兵值守人员发生意外而无人知晓。

</details>

<details><summary>SC-EMP-007 §6.5 · 6.5 通勤与人身安全提示</summary>

6.5 **通勤与人身安全提示。** 夜班员工在深夜通勤时应有相应的安全安排，如由站点协助安排安全的交通方式、结伴或报备到达，避免在僻静路段独自步行。夜间处理住户冲突、醉酒或情绪激动事件时，员工应保持安全距离、避免独处处理，必要时呼叫支援或联系保安/警方。夜班员工的人身安全与住户的人身安全同等重要，任何情况下都不应让值守人员冒险单独处置高风险事件。

</details>

## TC-V2-NIGHT-GENERAL-LOOKUP-01 夜班报备与冲突安全：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: NIGHT-GENERAL
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-EMP-007", "clause": "6.1", "anchor": "6.1 双人报备"}]
- **preferred_sources**: ["SC-EMP-007"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-EMP-007 第 6.1 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 夜班单兵在上下班和关键时间点向指定负责人或系统报备；失联按约定流程核查。 | required | (SC-EMP-007 §6.1) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-007"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-007 §6.1 · 6.1 双人报备</summary>

6.1 **双人报备。** 夜班与单兵岗位应实行"报备"制度，即值守员工在上班、下班以及关键时间点向指定的值班负责人或系统进行报备，以确认其在岗且安全。报备的方式可为定时打卡、系统签到、与当班调度确认等。若员工未能按时报备且无法联答，站点应按约定的失联处理流程启动核查，防止单兵值守人员发生意外而无人知晓。

</details>

