# POLICY-UPDATE：法规变化后的文件维护

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-POLICY-UPDATE-QA-01 法规变化后的文件维护

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: POLICY-UPDATE
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

> **问题：** 发现法规指引更新，能先凭记忆改一个数字上线吗？内部应走哪些更新步骤？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | Compliance Lead 记录来源生效日期并评估法定义务、流程和对外文件影响。 | required | (SC-REG-001 §6.2) |
| C2 | 受影响文档修订重发并标版本日期，重大变化培训告知；未核实细节不写入正文。 | required | (SC-REG-001 §6.2) |

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

<details><summary>SC-REG-001 §6.2 · 6.2 变更评估与文档修订</summary>

### 6.2 变更评估与文档修订

一旦发现法规/指引/标准变化，按以下流程处置：

1. **记录并评估**：由 Compliance Lead 记录变化来源、生效日期、受影响的主题（对照第 3 节地图）。
2. **判定影响**：判断变化是否影响 Safescan 的（a）法定义务，（b）内部流程，（c）对外文件（协议、住户守则、表单），还是（d）仅需知悉。
3. **修订文档**：若影响 (a)–(c)，更新对应属地手册/政策，更新后**重新发布并注明版本与修订日期**；凡涉及法定数字且无法在基线 A/C 节找到出处的，一律改写为"按州现行指引为准"。
4. **培训与告知**：将重大变化通过培训或公告告知受影响员工（学生线、长租线分别告知）。
5. **更新基线**：若属新的已核实事实，回报知识库维护者更新 kb_build/02 法规基线 A 节；未核实的新细节不得写入任何正文。

> 任何作者不得在知识库中文档里引用"本基线文件之外"的条号、天数、周数、金额。这是 Safescan 知识库的铁律，违反即为文档缺陷，须在复核中修正。

</details>

## TC-V2-POLICY-UPDATE-LOOKUP-01 法规变化后的文件维护：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: POLICY-UPDATE
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-REG-001", "clause": "6.2", "anchor": "6.2 变更评估与文档修订"}]
- **preferred_sources**: ["SC-REG-001"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-REG-001 第 6.2 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | Compliance Lead 记录来源生效日期并评估法定义务、流程和对外文件影响。 | required | (SC-REG-001 §6.2) |

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

<details><summary>SC-REG-001 §6.2 · 6.2 变更评估与文档修订</summary>

### 6.2 变更评估与文档修订

一旦发现法规/指引/标准变化，按以下流程处置：

1. **记录并评估**：由 Compliance Lead 记录变化来源、生效日期、受影响的主题（对照第 3 节地图）。
2. **判定影响**：判断变化是否影响 Safescan 的（a）法定义务，（b）内部流程，（c）对外文件（协议、住户守则、表单），还是（d）仅需知悉。
3. **修订文档**：若影响 (a)–(c)，更新对应属地手册/政策，更新后**重新发布并注明版本与修订日期**；凡涉及法定数字且无法在基线 A/C 节找到出处的，一律改写为"按州现行指引为准"。
4. **培训与告知**：将重大变化通过培训或公告告知受影响员工（学生线、长租线分别告知）。
5. **更新基线**：若属新的已核实事实，回报知识库维护者更新 kb_build/02 法规基线 A 节；未核实的新细节不得写入任何正文。

> 任何作者不得在知识库中文档里引用"本基线文件之外"的条号、天数、周数、金额。这是 Safescan 知识库的铁律，违反即为文档缺陷，须在复核中修正。

</details>

