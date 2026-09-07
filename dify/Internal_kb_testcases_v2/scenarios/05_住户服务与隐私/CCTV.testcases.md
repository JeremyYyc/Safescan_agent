# CCTV：住户申请查看录像

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-CCTV-QA-01 住户申请查看录像

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: CCTV
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-HSR-011"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 住户要求查看包含自己的监控，画面也有其他人，能直接发完整视频吗？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 应核验身份与合理范围，涉及他人隐私或执法等权益要遮挡处理或说明不能提供的合理理由。 | required | (SC-HSR-011 §4.4) |
| C2 | 员工不得私自调取复制外传录像，相关调查等用途也须按合规流程并在授权范围内。 | required | (SC-EMP-006 §8.4) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-HSR-011", "SC-EMP-006"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-HSR-011 §4.4 · 4.4 住户个人请求的边界</summary>

### 4.4 住户个人请求的边界

住户就自身影像或门禁数据提出的访问/更正/删除请求，应依 APPs 与相关法律处理。住户在其个人信息上享有查询、更正、删除等权利（受法律允许的例外），物业应在核验身份与合理范围内提供。但对于涉及他人隐私、安全、执法或第三人权益的画面，物业应作处理（如遮挡/去掉可识别他人信息）或说明无法提供的合理理由。住户申请调阅涉及争议事件（如投诉、损坏）的，应告知相关限制并指引；涉及监控录像作为证据的，按合规流程处理。住户对其数据的删除或更正请求，应在符合保留义务与法律要求范围内处理。

</details>

<details><summary>SC-EMP-006 §8.4 · 8.4 录像（CCTV）与门禁数据的处理</summary>

8.4 **录像（CCTV）与门禁数据的处理。** 站点 CCTV 与门禁系统记录的影像与刷卡记录，可能识别到个人，属于个人信息范畴。其安装与使用应基于安全与合法运营目的，并在公共区域设置提示；员工不得私自调取、复制或外传录像，除非在合规流程下（如为调查安全事故、处理住户投诉、回应执法请求且在授权范围内）。录像的保存期限与调阅权限由站点与合规按属地要求执行（详见 kb_build/02 法规基线 B 节，以官方指引为准）。

</details>

## TC-V2-CCTV-LOOKUP-01 住户申请查看录像：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: CCTV
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-HSR-011", "clause": "4.4", "anchor": "4.4 住户个人请求的边界"}]
- **preferred_sources**: ["SC-HSR-011"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-HSR-011 第 4.4 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 应核验身份与合理范围，涉及他人隐私或执法等权益要遮挡处理或说明不能提供的合理理由。 | required | (SC-HSR-011 §4.4) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-HSR-011"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-HSR-011 §4.4 · 4.4 住户个人请求的边界</summary>

### 4.4 住户个人请求的边界

住户就自身影像或门禁数据提出的访问/更正/删除请求，应依 APPs 与相关法律处理。住户在其个人信息上享有查询、更正、删除等权利（受法律允许的例外），物业应在核验身份与合理范围内提供。但对于涉及他人隐私、安全、执法或第三人权益的画面，物业应作处理（如遮挡/去掉可识别他人信息）或说明无法提供的合理理由。住户申请调阅涉及争议事件（如投诉、损坏）的，应告知相关限制并指引；涉及监控录像作为证据的，按合规流程处理。住户对其数据的删除或更正请求，应在符合保留义务与法律要求范围内处理。

</details>

