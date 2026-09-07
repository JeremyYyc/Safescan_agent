# CONDITION：退租损坏证据

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-CONDITION-QA-01 退租损坏证据

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: CONDITION
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-LGL-008"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 退租看到墙上划痕就能判定住户损坏并扣款吗？检查证据怎么整理？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 必须对照入住报告逐点区分新增损坏、未恶化既有缺陷和正常损耗，不能凭记忆。 | required | (SC-LGL-008 §5) |
| C2 | 记录位置程度并拍照归档关联条目，报告向住户说明确认，拟扣款交专项评估流程。 | required | (SC-LGL-008 §5) |

**forbidden_claims**

- 不得编造本轮证据没有提供的数字、个人记录、版本或联系方式。
- 不得将模拟内部政策当作已核验的现行法律。
- 不得引用未交给模型的文档或不支持结论的条款。
- 不得声称已执行申请、审批、付款或系统修改。
- 不得从单张照片直接作最终责任或扣款金额裁决。

**insufficient_evidence_behavior**

仅回答实际证据支持的部分并明确具体缺口，必要时转主管/资料维护人；完整问答缺少必答事实仍不通过。

**pass_criteria**

- 所有 required 事实被正确回答且至少一个完整证据选项实际进入模型上下文。
- 所有关键结论引用真实、适用、获授权的证据；禁止项一票否决。
- preferred_sources 未命中不单独判业务问答失败；新等价证据记 needs_review 后人工复核。

**evidence_review**

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-LGL-008"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-LGL-008 §5 · 5. 退租检查流程（Move-out）</summary>

## 5. 退租检查流程（Move-out）

退租检查是与入住报告的对照与扣款评估基础。完成时点为 **内部政策**：应在退租当日完成；情况复杂或多人共享单元时可适当延后，但须在押金退款提交前完成并保存。退租检查流程如下。

- **步骤 1：同步住户安排**。在住户搬离日前预约退租检查，说明验收要求与需搬空/清洁的范围。注意：住户应提前清空个人物品以利检查。完成标志：预约时间确认。
- **步骤 2：对照入住报告逐点检查**。逐一比对入住报告中的既有缺陷与当前状态，识别"新增损坏""已有缺陷未见恶化""正常损耗"三类。注意：必须持入住报告对照，不能凭记忆判断。完成标志：形成新增/未变化/损耗分类。
- **步骤 3：拍摄证据并记录**。对新增损坏、污染或缺失项目拍摄清晰照片/视频，记录具体位置与程度；对清洁不达标的区域记录并连同报价单留档。注意：及时抓拍当场状态，防止后续变化破坏证据。完成标志：证据已归档并关联对应房间条目。
- **步骤 4：返回登记与确认**。整理退租报告，向住户说明记录结果并请其确认；对拟扣款项，交由 SC-LGL-007 的扣款评估与确认流程。完成标志：报告归档，扣款项进入评估。

</details>

## TC-V2-CONDITION-LOOKUP-01 退租损坏证据：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: CONDITION
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-LGL-008", "clause": "5", "anchor": "5. 退租检查流程（Move-out）"}]
- **preferred_sources**: ["SC-LGL-008"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-LGL-008 第 5 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 必须对照入住报告逐点区分新增损坏、未恶化既有缺陷和正常损耗，不能凭记忆。 | required | (SC-LGL-008 §5) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-LGL-008"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-LGL-008 §5 · 5. 退租检查流程（Move-out）</summary>

## 5. 退租检查流程（Move-out）

退租检查是与入住报告的对照与扣款评估基础。完成时点为 **内部政策**：应在退租当日完成；情况复杂或多人共享单元时可适当延后，但须在押金退款提交前完成并保存。退租检查流程如下。

- **步骤 1：同步住户安排**。在住户搬离日前预约退租检查，说明验收要求与需搬空/清洁的范围。注意：住户应提前清空个人物品以利检查。完成标志：预约时间确认。
- **步骤 2：对照入住报告逐点检查**。逐一比对入住报告中的既有缺陷与当前状态，识别"新增损坏""已有缺陷未见恶化""正常损耗"三类。注意：必须持入住报告对照，不能凭记忆判断。完成标志：形成新增/未变化/损耗分类。
- **步骤 3：拍摄证据并记录**。对新增损坏、污染或缺失项目拍摄清晰照片/视频，记录具体位置与程度；对清洁不达标的区域记录并连同报价单留档。注意：及时抓拍当场状态，防止后续变化破坏证据。完成标志：证据已归档并关联对应房间条目。
- **步骤 4：返回登记与确认**。整理退租报告，向住户说明记录结果并请其确认；对拟扣款项，交由 SC-LGL-007 的扣款评估与确认流程。完成标志：报告归档，扣款项进入评估。

</details>

