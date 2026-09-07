# PAYSLIP：工资单差异反馈

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-PAYSLIP-QA-01 工资单差异反馈

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: PAYSLIP
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-EMP-002"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 工资单工时和我记录的不一致，应该找谁核对？过了公司建议反馈时间是不是就不能纠正？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 应核对工资单，发现问题联系人力资源部；付薪或加班费率疑问向主管或 HR 提出。 | required | (SC-EMP-002 §6.1 AND SC-EMP-002 §6.2) |
| C2 | 收到后 10 个工作日内反馈是内部标准，逾期未反馈不免除雇主核正责任。 | required | (SC-EMP-002 §6.2) |

**forbidden_claims**

- 不得编造本轮证据没有提供的数字、个人记录、版本或联系方式。
- 不得将模拟内部政策当作已核验的现行法律。
- 不得引用未交给模型的文档或不支持结论的条款。
- 不得声称已执行申请、审批、付款或系统修改。
- 不得将内部反馈时间说成法定索赔期限或逾期自动丧失权利。

**insufficient_evidence_behavior**

仅回答实际证据支持的部分并明确具体缺口，必要时转主管/资料维护人；完整问答缺少必答事实仍不通过。

**pass_criteria**

- 所有 required 事实被正确回答且至少一个完整证据选项实际进入模型上下文。
- 所有关键结论引用真实、适用、获授权的证据；禁止项一票否决。
- preferred_sources 未命中不单独判业务问答失败；新等价证据记 needs_review 后人工复核。

**evidence_review**

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-002"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-002 §6.1 · 6.1 工资单（Payslip）</summary>

6.1 **工资单（Payslip）。** 每次支付工资，Safescan 应向员工提供工资单，内容包括：雇主与员工身份、支付周期、付薪日期、工资总额与各项扣除明细、加班/补贴明细、应发与实发金额、累计年假/病假等余额或相关说明。工资单以电子形式发放到员工登记的系统或邮箱，员工应妥善保管并可随时查阅，发现问题及时联系人力资源部。

</details>

<details><summary>SC-EMP-002 §6.2 · 6.2 工资单的准确性义务</summary>

6.2 **工资单的准确性义务。** 员工有责任核对每期工资单，发现工时记录或计算差异应在合理时间内（内部标准：收到后 10 个工作日内）反馈，以便更正；逾期未反馈不代表雇主免除核正责任，但及时反馈有助于快速处理差错。涉及付薪标准、加班费率的疑问，应向主管或人力资源部提出，而非在私下猜测或传播未经核实的说法。

</details>

## TC-V2-PAYSLIP-LOOKUP-01 工资单差异反馈：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: PAYSLIP
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-EMP-002", "clause": "6.1", "anchor": "6.1 工资单（Payslip）"}, {"doc_id": "SC-EMP-002", "clause": "6.2", "anchor": "6.2 工资单的准确性义务"}]
- **preferred_sources**: ["SC-EMP-002"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-EMP-002 第 6.1 条/节、SC-EMP-002 第 6.2 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 应核对工资单，发现问题联系人力资源部；付薪或加班费率疑问向主管或 HR 提出。 | required | (SC-EMP-002 §6.1 AND SC-EMP-002 §6.2) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-002"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-002 §6.1 · 6.1 工资单（Payslip）</summary>

6.1 **工资单（Payslip）。** 每次支付工资，Safescan 应向员工提供工资单，内容包括：雇主与员工身份、支付周期、付薪日期、工资总额与各项扣除明细、加班/补贴明细、应发与实发金额、累计年假/病假等余额或相关说明。工资单以电子形式发放到员工登记的系统或邮箱，员工应妥善保管并可随时查阅，发现问题及时联系人力资源部。

</details>

<details><summary>SC-EMP-002 §6.2 · 6.2 工资单的准确性义务</summary>

6.2 **工资单的准确性义务。** 员工有责任核对每期工资单，发现工时记录或计算差异应在合理时间内（内部标准：收到后 10 个工作日内）反馈，以便更正；逾期未反馈不代表雇主免除核正责任，但及时反馈有助于快速处理差错。涉及付薪标准、加班费率的疑问，应向主管或人力资源部提出，而非在私下猜测或传播未经核实的说法。

</details>

