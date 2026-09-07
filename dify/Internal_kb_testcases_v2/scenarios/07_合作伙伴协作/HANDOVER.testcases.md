# HANDOVER：承包商验收单

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-HANDOVER-QA-01 承包商验收单

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: HANDOVER
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-TRN-008"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 维保商完工后验收单应留什么记录？谁签字，验收不过怎么处理？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 验收单记录作业及人员、时间材料、结论、遗留问题、后续安排和质保说明，由承包商与公司验收人签字。 | required | (SC-TRN-008 §6) |
| C2 | 不合格注明问题并返工跟踪，整体不达标重新作业并记不符合项；不能无验收直接视为履约完成。 | required | (SC-TRN-008 §6) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-TRN-008"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-TRN-008 §6 · 6. 完工验收单与住户确认</summary>

## 6. 完工验收单与住户确认

维保完成后，须进行完工验收并签署**完工验收单（Completion / Handover Sheet）**，作为质量确认、付款与质保起算的依据。验收由 Facilities Coordinator 或指定人员执行，确认问题已解决、质量达标、符合安全与规范、无二次隐患；重大或复杂维修须现场核查，简单维修可通过住户确认。验收单须记录：作业内容、作业方与人员、完成时间、使用材料、验收结论、遗留问题与后续安排，以及质保期起算与说明，由承包商与 Safescan 验收人双方签字。

对进入住户房间的维修，验收后应请住户确认并记录其满意度；住户确认无误则关闭工单。若住户对结果不满意，须记录其具体意见，评估是否需要返工或升级，不得以"已修完"为由忽略住户合理诉求。凡涉及费用或扣款的，仅对"住户责任损坏"且符合条件并经住户同意才转 SC-LGL-007 流程（见 SC-SOP-009 第 5.5 节）。

验收不合格的处理：对单项不合规（如清洁不到位、装饰错位、小小瑕疵），注明问题、限期返工并跟踪；对整体不达标（问题未解决、存在安全隐患、质量明显不符）的，要求承包商返工或重新作业，并记为一次不符合项。返工原则上不计住户费用（除非属住户新增损坏），属承包商质保或履约责任（见第 9 节）。对验收中发现的工单外问题，由 Facilities Coordinator 评估是否新增工单或属损坏责任，不得擅自扩大维修或漏记，避免"顺带改动"导致责任不清。

</details>

## TC-V2-HANDOVER-LOOKUP-01 承包商验收单：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: HANDOVER
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-TRN-008", "clause": "6", "anchor": "6. 完工验收单与住户确认"}]
- **preferred_sources**: ["SC-TRN-008"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-TRN-008 第 6 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 验收单记录作业及人员、时间材料、结论、遗留问题、后续安排和质保说明，由承包商与公司验收人签字。 | required | (SC-TRN-008 §6) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-TRN-008"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-TRN-008 §6 · 6. 完工验收单与住户确认</summary>

## 6. 完工验收单与住户确认

维保完成后，须进行完工验收并签署**完工验收单（Completion / Handover Sheet）**，作为质量确认、付款与质保起算的依据。验收由 Facilities Coordinator 或指定人员执行，确认问题已解决、质量达标、符合安全与规范、无二次隐患；重大或复杂维修须现场核查，简单维修可通过住户确认。验收单须记录：作业内容、作业方与人员、完成时间、使用材料、验收结论、遗留问题与后续安排，以及质保期起算与说明，由承包商与 Safescan 验收人双方签字。

对进入住户房间的维修，验收后应请住户确认并记录其满意度；住户确认无误则关闭工单。若住户对结果不满意，须记录其具体意见，评估是否需要返工或升级，不得以"已修完"为由忽略住户合理诉求。凡涉及费用或扣款的，仅对"住户责任损坏"且符合条件并经住户同意才转 SC-LGL-007 流程（见 SC-SOP-009 第 5.5 节）。

验收不合格的处理：对单项不合规（如清洁不到位、装饰错位、小小瑕疵），注明问题、限期返工并跟踪；对整体不达标（问题未解决、存在安全隐患、质量明显不符）的，要求承包商返工或重新作业，并记为一次不符合项。返工原则上不计住户费用（除非属住户新增损坏），属承包商质保或履约责任（见第 9 节）。对验收中发现的工单外问题，由 Facilities Coordinator 评估是否新增工单或属损坏责任，不得擅自扩大维修或漏记，避免"顺带改动"导致责任不清。

</details>

