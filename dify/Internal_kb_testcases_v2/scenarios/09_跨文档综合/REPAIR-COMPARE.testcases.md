# REPAIR-COMPARE：维修复核与验收单衔接

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-REPAIR-COMPARE-COMPARE-01 维修复核与验收单衔接

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: REPAIR-COMPARE
- **origin_case_ids**: []
- **test_goal**: cross_document_qa
- **question_type**: ["cross_doc", "process_qa", "boundary"]
- **difficulty**: 难
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-SOP-009", "clause": "5.5.1", "anchor": "5.5.1 操作"}, {"doc_id": "SC-SOP-009", "clause": "5.5.2", "anchor": "5.5.2 说明"}, {"doc_id": "SC-TRN-008", "clause": "6", "anchor": "6. 完工验收单与住户确认"}]
- **preferred_sources**: ["SC-SOP-009"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请对照 SC-SOP-009 第5.5.1—5.5.2条和 SC-TRN-008 第6节，整理维修工单复核、承包商验收单及住户确认的衔接。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 工单关闭前复核维修效果，住户有异议须记录并评估返工升级。 | required | (SC-SOP-009 §5.5.1 AND SC-SOP-009 §5.5.2) |
| C2 | 承包商与公司验收人签署含工作材料、结论遗留事项和质保说明的验收单，并衔接住户确认。 | required | (SC-TRN-008 §6) |

**forbidden_claims**

- 不得编造本轮证据没有提供的数字、个人记录、版本或联系方式。
- 不得将模拟内部政策当作已核验的现行法律。
- 不得引用未交给模型的文档或不支持结论的条款。
- 不得声称已执行申请、审批、付款或系统修改。

**insufficient_evidence_behavior**

仅回答实际证据支持的部分并明确具体缺口，必要时转主管/资料维护人；完整问答缺少必答事实仍不通过。

**pass_criteria**

- 用户明确要求的 required_targets 均须实际取得，完成对比或流程衔接，不能只引用其中一篇。
- 所有 required 事实被正确回答且至少一个完整证据选项实际进入模型上下文。
- 所有关键结论引用真实、适用、获授权的证据；禁止项一票否决。
- preferred_sources 未命中不单独判业务问答失败；新等价证据记 needs_review 后人工复核。

**evidence_review**

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-SOP-009", "SC-TRN-008"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-SOP-009 §5.5.1 · 5.5.1 操作</summary>

5.5.1 **操作：** Facilities Coordinator 或指定人员对维修结果复核：确认问题已解决、质量达标、符合安全与规范、无二次隐患。重大或复杂维修须现场核查；简单维修可通过住户确认。复核通过后，请住户确认并记录其满意度；住户确认无误则关闭工单。

</details>

<details><summary>SC-SOP-009 §5.5.2 · 5.5.2 说明</summary>

5.5.2 **说明：** 完工复核是质量控制与责任界定的关键。复核不通过则触发返工（见 5.6）。若住户对结果不满意，记录其具体意见，评估是否需要返工或升级；不得以"已修完"为由忽略住户合理诉求。涉及费用或扣款的，仅对"住户责任损坏"才转 SC-LGL-007。

</details>

<details><summary>SC-TRN-008 §6 · 6. 完工验收单与住户确认</summary>

## 6. 完工验收单与住户确认

维保完成后，须进行完工验收并签署**完工验收单（Completion / Handover Sheet）**，作为质量确认、付款与质保起算的依据。验收由 Facilities Coordinator 或指定人员执行，确认问题已解决、质量达标、符合安全与规范、无二次隐患；重大或复杂维修须现场核查，简单维修可通过住户确认。验收单须记录：作业内容、作业方与人员、完成时间、使用材料、验收结论、遗留问题与后续安排，以及质保期起算与说明，由承包商与 Safescan 验收人双方签字。

对进入住户房间的维修，验收后应请住户确认并记录其满意度；住户确认无误则关闭工单。若住户对结果不满意，须记录其具体意见，评估是否需要返工或升级，不得以"已修完"为由忽略住户合理诉求。凡涉及费用或扣款的，仅对"住户责任损坏"且符合条件并经住户同意才转 SC-LGL-007 流程（见 SC-SOP-009 第 5.5 节）。

验收不合格的处理：对单项不合规（如清洁不到位、装饰错位、小小瑕疵），注明问题、限期返工并跟踪；对整体不达标（问题未解决、存在安全隐患、质量明显不符）的，要求承包商返工或重新作业，并记为一次不符合项。返工原则上不计住户费用（除非属住户新增损坏），属承包商质保或履约责任（见第 9 节）。对验收中发现的工单外问题，由 Facilities Coordinator 评估是否新增工单或属损坏责任，不得擅自扩大维修或漏记，避免"顺带改动"导致责任不清。

</details>

