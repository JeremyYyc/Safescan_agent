# GOVERNANCE：组织分层与站点指挥

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-GOVERNANCE-QA-01 组织分层与站点指挥

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: GOVERNANCE
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-EMP-001"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 总部、区域和站点分别负责哪一层管理？站点对外承诺找谁统一把关？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 公司采用总部—区域—站点三层结构，分别承担战略政策、跨站协调和日常执行。 | required | (SC-EMP-001 §3.1) |
| C2 | 站点对外承诺须经过 Property Manager 或其明确授权的人，超岗位权限应升级。 | required | (SC-EMP-001 §3.4) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-001"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-001 §3.1 · 3.1 三层设计</summary>

3.1 **三层设计。** Safescan 采用"集团总部—区域—站点"三层结构。总部处于战略与政策制定层，负责确定集团统一标准（定价框架、合规基线、品牌形象、系统平台）、审批重大资本与合同事项、任免站点负责人；区域层承担管理跨度，负责跨站点资源调配、站点绩效对标、区域性的应急联络与政府/校方关系；站点层是日常经营与对客服务的执行层。任何站点问题应当先按"站点内部→区域→总部"的顺序升级，除非属于必须第一时间直达总部的事件（如重大媒体事件、重大安全事故、潜在法律诉讼、数据泄露）。

</details>

<details><summary>SC-EMP-001 §3.4 · 3.4 站点层"一个出口"原则</summary>

3.4 **站点层"一个出口"原则。** 为保证对客口径统一，每一站点对外有一名"站点头"（Property Manager）。对外承诺、媒体应答、执法机构接待、重大合同签署，均须经过 Property Manager 或其明确授权的人（见第 8 节四问原则）。普通员工遇到超出本岗位权限的询问（如媒体采访、政府检查、住户要求书面保证某项权益），应停止作答并升级，而不是现场给出口头承诺。

</details>

## TC-V2-GOVERNANCE-LOOKUP-01 组织分层与站点指挥：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: GOVERNANCE
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-EMP-001", "clause": "3.1", "anchor": "3.1 三层设计"}]
- **preferred_sources**: ["SC-EMP-001"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-EMP-001 第 3.1 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 公司采用总部—区域—站点三层结构，分别承担战略政策、跨站协调和日常执行。 | required | (SC-EMP-001 §3.1) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-001"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-001 §3.1 · 3.1 三层设计</summary>

3.1 **三层设计。** Safescan 采用"集团总部—区域—站点"三层结构。总部处于战略与政策制定层，负责确定集团统一标准（定价框架、合规基线、品牌形象、系统平台）、审批重大资本与合同事项、任免站点负责人；区域层承担管理跨度，负责跨站点资源调配、站点绩效对标、区域性的应急联络与政府/校方关系；站点层是日常经营与对客服务的执行层。任何站点问题应当先按"站点内部→区域→总部"的顺序升级，除非属于必须第一时间直达总部的事件（如重大媒体事件、重大安全事故、潜在法律诉讼、数据泄露）。

</details>

