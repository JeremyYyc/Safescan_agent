# PRIVACY-COMPARE：员工与住户记录边界

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-PRIVACY-COMPARE-COMPARE-01 员工与住户记录边界

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: PRIVACY-COMPARE
- **origin_case_ids**: []
- **test_goal**: cross_document_qa
- **question_type**: ["cross_doc", "process_qa", "boundary"]
- **difficulty**: 难
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-EMP-006", "clause": "4.2", "anchor": "4.2 员工数据的边界与\"记录陷阱\""}, {"doc_id": "SC-REG-008", "clause": "3.3", "anchor": "3.3 员工既是员工也是住户的情形"}]
- **preferred_sources**: ["SC-EMP-006"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请对照 SC-EMP-006 第4.2条与 SC-REG-008 第3.3条：员工同时住在公司公寓，是否所有信息都可按雇佣记录处理？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 员工档案也受岗位相关与业务目的访问限制，主管不能无正当目的查看。 | required | (SC-EMP-006 §4.2) |
| C2 | 同一人作为住户产生的数据按住户数据处理，雇佣记录按员工记录处理，两类清晰分离。 | required | (SC-REG-008 §3.3) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-006", "SC-REG-008"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-006 §4.2 · 4.2 员工数据的边界与"记录陷阱"</summary>

4.2 **员工数据的边界与"记录陷阱"。** 员工档案（工资、假期、绩效、纪律）主要为雇佣管理服务，但并不意味着可以随意查看或外传。员工只能访问与自身岗位相关的员工数据：直属上级可查看排班与考勤，HR 可查看工资与假期，单位负责人可查看与其职责相关的信息。任何员工不得为满足个人好奇心而查看其他同事的工资、病假或纪律记录，包括直属上级也不得在无正当业务目的时查看下属的敏感个人信息——这就是所谓的"员工记录陷阱"。

</details>

<details><summary>SC-REG-008 §3.3 · 3.3 员工既是员工也是住户的情形</summary>

3.3 **员工既是员工也是住户的情形**：员工若同时是住户（如宿舍宿管），其作为住户产生的数据按住户数据处理；其作为员工产生的雇佣记录按员工记录处理。两者界限必须清晰分离，优先适用各自规则中更严格者。

</details>

