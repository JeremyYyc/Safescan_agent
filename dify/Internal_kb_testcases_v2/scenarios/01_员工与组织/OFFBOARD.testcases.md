# OFFBOARD：离职权限与资料回收

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-OFFBOARD-QA-01 离职权限与资料回收

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: OFFBOARD
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

> **问题：** 员工离职后可以留一份住户名单方便以后交接吗？公司应回收哪些系统访问？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 离职不得保留住户和业务数据副本，保密义务持续。 | required | (SC-EMP-006 §9.3) |
| C2 | IT 与 HR/站点协调停用账号、邮箱、VPN，回收门卡钥匙设备并取消远程访问。 | required | (SC-EMP-006 §9.3) |

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

<details><summary>SC-EMP-006 §9.3 · 9.3 离职的信息回收</summary>

9.3 **离职的信息回收。** 员工离职时，由 IT 与 HR/站点协调完成信息权限回收：立即停用系统账号、邮箱与 VPN，回收门禁卡与钥匙，收回公司设备与可移动介质，并取消远程访问。员工的最后工作日应完成交接，将持有的住户与业务数据交接给指定接任者，禁止在离职后保留任何副本。离职后，员工对在职期间获知的保密信息仍负有持续保密义务，本政策中的保密义务不因劳动关系结束而终止。（本政策应与 SC-EMP-009 离职流程联动执行。）

</details>

## TC-V2-OFFBOARD-LOOKUP-01 离职权限与资料回收：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: OFFBOARD
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-EMP-006", "clause": "9.3", "anchor": "9.3 离职的信息回收"}]
- **preferred_sources**: ["SC-EMP-006"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-EMP-006 第 9.3 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 离职不得保留住户和业务数据副本，保密义务持续。 | required | (SC-EMP-006 §9.3) |

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

<details><summary>SC-EMP-006 §9.3 · 9.3 离职的信息回收</summary>

9.3 **离职的信息回收。** 员工离职时，由 IT 与 HR/站点协调完成信息权限回收：立即停用系统账号、邮箱与 VPN，回收门禁卡与钥匙，收回公司设备与可移动介质，并取消远程访问。员工的最后工作日应完成交接，将持有的住户与业务数据交接给指定接任者，禁止在离职后保留任何副本。离职后，员工对在职期间获知的保密信息仍负有持续保密义务，本政策中的保密义务不因劳动关系结束而终止。（本政策应与 SC-EMP-009 离职流程联动执行。）

</details>

