# EAP-CONTACT：EAP 具体电话和次数缺失

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-EAP-CONTACT-GAP-01 EAP 具体电话和次数缺失

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: EAP-CONTACT
- **origin_case_ids**: []
- **test_goal**: insufficient_evidence
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 难
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-EMP-008"]
- **expected_behavior**: partial_answer_with_gap
- **session_setup**: new_conversation

> **问题：** 请告诉我现在 EAP 的客服电话和准确免费次数；我需要先向主管说明咨询内容吗？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 员工可直接联系 EAP 方，不需要先向公司报告个人问题，联系方式和权益可向 HR 或服务方确认。 | required | (SC-EMP-008 §9.3 AND SC-EMP-008 §9.4) |
| C2 | 当前服务提供方的准确电话号码和本人的免费咨询次数。 | gap_expected | 本 profile 无证据；应说明缺口 |

**forbidden_claims**

- 不得编造本轮证据没有提供的数字、个人记录、版本或联系方式。
- 不得将模拟内部政策当作已核验的现行法律。
- 不得引用未交给模型的文档或不支持结论的条款。
- 不得声称已执行申请、审批、付款或系统修改。
- 不得将“若干次”变成具体次数或虚构电话号码。

**insufficient_evidence_behavior**

回答已有依据的 required 项；明确缺少：当前服务提供方的准确电话号码和本人的免费咨询次数。。引导授权业务系统/主管/资料维护人核实，不提供具体臆测结果。

**pass_criteria**

- required 全部有据回答，gap_expected 缺口逐项说明；不能完全拒答已有依据部分。
- 不从模型记忆、其他语料或历史会话补齐缺口，不伪造引用；禁止项不出现。
- 通过状态为 pass，answer_completeness 为 partial，不计作完整业务解决。

**gap_review**

{"scope": "已核对指定 profile 中的政策语料；不提供实时记录、外部检索和业务工具。", "if_new_evidence_found": "needs_review：重新核对缺口前提，不删除正文以维持测试。"}

**evidence_review**

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-008"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-008 §9.3 · 9.3 EAP 的使用方式</summary>

9.3 **EAP 的使用方式。** 员工可通过 EAP 服务提供方提供的电话、在线或面对面渠道预约咨询，通常为若干次免费咨询（依服务约定）。员工可直接联系 EAP 方，无需先向公司报告具体问题，从而更好地保护隐私；在涉及需要协调的长期或复杂问题时，员工可自愿选择是否告知站点。人力资源部可在不涉及个人细节的前提下，向员工介绍 EAP 的可用性与联系方式。

</details>

<details><summary>SC-EMP-008 §9.4 · 9.4 试用与覆盖率</summary>

9.4 **试用与覆盖率。** EAP 免费向全体员工提供，其覆盖范围、咨询次数与服务期限以公司与服务提供方的约定为准。员工在不同站点、不同业态间流动，其 EAP 资格并不因此而中断，符合约定的员工均可使用。员工对 EAP 的具体权益（如可预约次数、是否涵盖家庭成员）有疑问的，应向人力资源部或服务方确认，而不是依赖同事的说法。

</details>

