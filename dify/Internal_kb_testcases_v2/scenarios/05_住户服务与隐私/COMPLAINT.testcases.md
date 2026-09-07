# COMPLAINT：投诉首响与调查回避

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-COMPLAINT-QA-01 投诉首响与调查回避

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: COMPLAINT
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-HSR-009"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 住户向前台投诉噪音，首次回复的时限是什么性质？如果投诉人是我朋友，我能负责调查吗？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 常规投诉登记后一个工作日内初步回应，安全紧急投诉即时响应；这是内部标准，首响不等于最终结论。 | required | (SC-HSR-009 §3.1) |
| C2 | 调查人有亲友或其他利害关系应回避，由值班或物业经理指定中立且有权人员。 | required | (SC-HSR-009 §4.3) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-HSR-009"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-HSR-009 §3.1 · 3.1 首响时限</summary>

### 3.1 首响时限

Safescan 对投诉的首次响应（首响）设置内部服务标准如下（Safescan 政策，非法规要求）：常规投诉自登记起在 1 个工作日内作出初步响应；涉及安全或紧急的投诉，应即时响应并优先处置。首响的目的在于让投诉人知悉物业已受理、正在处理，而非立即给出最终结论。首响可由受理人员通过电话、门户或邮件完成，并告知投诉预计的处理时间表与下一步安排。首响应清晰、礼貌、坦诚，避免让住户产生被敷衍或拖延的感受。

各站点应结合人员配置与投诉量设定首响与处理的目标时限，并向住户简要说明。首响应尽量在受理后尽早完成，避免因排队或转办造成拖延；涉及跨部门或多层级处理的，首响应说明将由哪一环节、哪位负责人跟进。面向所有业务线，首响时限一致适用，但因业务线差异，处理深度与转办路径可能不同。

</details>

<details><summary>SC-HSR-009 §4.3 · 4.3 中立取证与利益回避</summary>

### 4.3 中立取证与利益回避

为保证调查公正，调查人应保持中立，不偏袒任何一方。若调查人本人与投诉人或被投诉人存在利害关系（如为当事人亲友、直接责任人、或曾处理过相关争执），应回避，由他人接手调查。值班经理或物业经理应指定相对中立、有权处理该事项的人员负责调查。对涉及员工责任或设备责任的投诉，调查人应确认其与责任对象的独立性，避免自证。

利益回避还应体现在处理流程上：调查与裁决分离。负责调查事实与收集证据的人员，与负责作出处理决定（如是否处分、是否赔偿）的人员应适当区分，或至少保证处理决定基于调查结果而非主观偏好。这样既能保障公平，也为可能的申诉/复议提供依据。

</details>

## TC-V2-COMPLAINT-LOOKUP-01 投诉首响与调查回避：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: COMPLAINT
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-HSR-009", "clause": "3.1", "anchor": "3.1 首响时限"}]
- **preferred_sources**: ["SC-HSR-009"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-HSR-009 第 3.1 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 常规投诉登记后一个工作日内初步回应，安全紧急投诉即时响应；这是内部标准，首响不等于最终结论。 | required | (SC-HSR-009 §3.1) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-HSR-009"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-HSR-009 §3.1 · 3.1 首响时限</summary>

### 3.1 首响时限

Safescan 对投诉的首次响应（首响）设置内部服务标准如下（Safescan 政策，非法规要求）：常规投诉自登记起在 1 个工作日内作出初步响应；涉及安全或紧急的投诉，应即时响应并优先处置。首响的目的在于让投诉人知悉物业已受理、正在处理，而非立即给出最终结论。首响可由受理人员通过电话、门户或邮件完成，并告知投诉预计的处理时间表与下一步安排。首响应清晰、礼貌、坦诚，避免让住户产生被敷衍或拖延的感受。

各站点应结合人员配置与投诉量设定首响与处理的目标时限，并向住户简要说明。首响应尽量在受理后尽早完成，避免因排队或转办造成拖延；涉及跨部门或多层级处理的，首响应说明将由哪一环节、哪位负责人跟进。面向所有业务线，首响时限一致适用，但因业务线差异，处理深度与转办路径可能不同。

</details>

