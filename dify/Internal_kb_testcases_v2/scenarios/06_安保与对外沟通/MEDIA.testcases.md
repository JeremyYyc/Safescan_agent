# MEDIA：危机对外发言

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-MEDIA-QA-01 危机对外发言

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: MEDIA
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-SAF-014"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 重大事件后记者来询问，我作为值班员工可以代表公司确认原因吗？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 未经授权不得代表公司发布危机信息，由指定唯一授权发言人统一对外。 | required | (SC-SAF-014 §3.1) |
| C2 | 发言人联动 CIMT 核实进展，特别重大或敏感法律监管事项由集团管理层和法律合规把关。 | required | (SC-SAF-014 §3.2) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-SAF-014"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-SAF-014 §3.1 · 3.1 唯一授权发言人</summary>

3.1 **唯一授权发言人**：公司指定集团公共事务与传播部负责人（或授予的授权发言人）为重大事件的唯一对外授权发言人，统一代表公司对外发表声明、接受媒体询问、发布信息与澄清。其他任何岗位与人员在未经授权的情况下，不得代表公司对外表态或发布危机相关信息。

</details>

<details><summary>SC-SAF-014 §3.2 · 3.2 授权链与职责</summary>

3.2 **授权链与职责**：授权发言人负责评估事件敏感度、制定并发布对外口径、协调媒体关系、审查对外材料、并代表公司回应外部询问；授权发言人应与 CIMT（见 SC-SAF-001）保持联动，掌握事件事实、进展与处置情况，以确保口径准确。对特别重大或涉及法律、监管、敏感信息的，应上报集团管理层和法律/合规人员把关。

</details>

## TC-V2-MEDIA-LOOKUP-01 危机对外发言：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: MEDIA
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-SAF-014", "clause": "3.1", "anchor": "3.1 唯一授权发言人"}]
- **preferred_sources**: ["SC-SAF-014"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-SAF-014 第 3.1 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 未经授权不得代表公司发布危机信息，由指定唯一授权发言人统一对外。 | required | (SC-SAF-014 §3.1) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-SAF-014"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-SAF-014 §3.1 · 3.1 唯一授权发言人</summary>

3.1 **唯一授权发言人**：公司指定集团公共事务与传播部负责人（或授予的授权发言人）为重大事件的唯一对外授权发言人，统一代表公司对外发表声明、接受媒体询问、发布信息与澄清。其他任何岗位与人员在未经授权的情况下，不得代表公司对外表态或发布危机相关信息。

</details>

