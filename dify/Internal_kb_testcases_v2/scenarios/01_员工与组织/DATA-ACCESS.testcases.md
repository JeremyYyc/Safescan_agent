# DATA-ACCESS：员工数据最小访问

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-DATA-ACCESS-QA-01 员工数据最小访问

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: DATA-ACCESS
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-EMP-006"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 我是主管，能不能因为好奇查看同事病假和工资？需要额外权限时该怎么申请？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 员工记录不能随意查看，访问必须与岗位和正当业务目的相关，主管身份不代表可任意看敏感信息。 | required | (SC-EMP-006 §4.2) |
| C2 | 提升权限须由直属上级提出，经信息安全与隐私办公室或数据 owner 审批并记录。 | required | (SC-EMP-006 §4.4) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-006"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-006 §4.2 · 4.2 员工数据的边界与"记录陷阱"</summary>

4.2 **员工数据的边界与"记录陷阱"。** 员工档案（工资、假期、绩效、纪律）主要为雇佣管理服务，但并不意味着可以随意查看或外传。员工只能访问与自身岗位相关的员工数据：直属上级可查看排班与考勤，HR 可查看工资与假期，单位负责人可查看与其职责相关的信息。任何员工不得为满足个人好奇心而查看其他同事的工资、病假或纪律记录，包括直属上级也不得在无正当业务目的时查看下属的敏感个人信息——这就是所谓的"员工记录陷阱"。

</details>

<details><summary>SC-EMP-006 §4.4 · 4.4 访问控制与权限审批</summary>

4.4 **访问控制与权限审批。** 访问控制遵循"按岗位最低必需（least privilege）"原则：员工只获得履行其职责所必需的权限，且权限随岗位变动即时调整。需要提升权限的，须由直属上级提出、经信息安全与隐私办公室或对应的数据 owner 审批并记录。例如，Property Manager 可查看所在站点住户与员工的常规运营数据，但若要导出全站住户清单用于外部用途，则须升级到区域经理与合规岗审批。

</details>

## TC-V2-DATA-ACCESS-LOOKUP-01 员工数据最小访问：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: DATA-ACCESS
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-EMP-006", "clause": "4.2", "anchor": "4.2 员工数据的边界与\"记录陷阱\""}]
- **preferred_sources**: ["SC-EMP-006"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-EMP-006 第 4.2 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 员工记录不能随意查看，访问必须与岗位和正当业务目的相关，主管身份不代表可任意看敏感信息。 | required | (SC-EMP-006 §4.2) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-006"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-006 §4.2 · 4.2 员工数据的边界与"记录陷阱"</summary>

4.2 **员工数据的边界与"记录陷阱"。** 员工档案（工资、假期、绩效、纪律）主要为雇佣管理服务，但并不意味着可以随意查看或外传。员工只能访问与自身岗位相关的员工数据：直属上级可查看排班与考勤，HR 可查看工资与假期，单位负责人可查看与其职责相关的信息。任何员工不得为满足个人好奇心而查看其他同事的工资、病假或纪律记录，包括直属上级也不得在无正当业务目的时查看下属的敏感个人信息——这就是所谓的"员工记录陷阱"。

</details>

