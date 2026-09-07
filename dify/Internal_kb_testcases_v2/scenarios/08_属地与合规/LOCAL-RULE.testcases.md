# LOCAL-RULE：属地和业务线适用

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-LOCAL-RULE-QA-01 属地和业务线适用

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: LOCAL-RULE
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-REG-001"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 别州站点用的流程能直接复制到 NSW 吗？学生线和长租线可以不区分吗？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 法定事项按物业所在州现行法，公司统一标准仅在不冲突时适用。 | required | (SC-REG-001 §8.1) |
| C2 | 学生与长租差异须分别表述并说明原因，不能跨业务线混用。 | required | (SC-REG-001 §8.1) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-REG-001"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-REG-001 §8.1 · 8.1 "属地优先"原则</summary>

### 8.1 "属地优先"原则

Safescan 多州、双业务线运营，最易出错的是"拿一州规则套另一州"。因此统一采用**属地优先**三原则：

1. **属地法律优先于公司统一偏好**：凡法定事项，以物业所在州的现行法律为准；公司内部标准（如我们自己的服务响应时限）只在不与属地法规冲突的前提下适用。
2. **协议条款叠加属地法律**：学生线（PBSA）除州租赁法外还并入 Safescan 学生住宿附加条款；凡协议与州法不一致，以对住户权益更有利或属地法要求为准（对内提示，最终以官方与法务解释为准）。
3. **双线差异必须写明**：学生线与长租线对同一事项（预订单订金、押金、宠物、U18、家暴终止等）要求不同时，必须在流程中分别表述并说明原因（学生线受州租赁法/学校协议约束、楼宇分区管理等），不得混用。

</details>

## TC-V2-LOCAL-RULE-LOOKUP-01 属地和业务线适用：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: LOCAL-RULE
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-REG-001", "clause": "8.1", "anchor": "8.1 \"属地优先\"原则"}]
- **preferred_sources**: ["SC-REG-001"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-REG-001 第 8.1 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 法定事项按物业所在州现行法，公司统一标准仅在不冲突时适用。 | required | (SC-REG-001 §8.1) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-REG-001"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-REG-001 §8.1 · 8.1 "属地优先"原则</summary>

### 8.1 "属地优先"原则

Safescan 多州、双业务线运营，最易出错的是"拿一州规则套另一州"。因此统一采用**属地优先**三原则：

1. **属地法律优先于公司统一偏好**：凡法定事项，以物业所在州的现行法律为准；公司内部标准（如我们自己的服务响应时限）只在不与属地法规冲突的前提下适用。
2. **协议条款叠加属地法律**：学生线（PBSA）除州租赁法外还并入 Safescan 学生住宿附加条款；凡协议与州法不一致，以对住户权益更有利或属地法要求为准（对内提示，最终以官方与法务解释为准）。
3. **双线差异必须写明**：学生线与长租线对同一事项（预订单订金、押金、宠物、U18、家暴终止等）要求不同时，必须在流程中分别表述并说明原因（学生线受州租赁法/学校协议约束、楼宇分区管理等），不得混用。

</details>

