# AGENT：代理代签与信息用途

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-AGENT-QA-01 代理代签与信息用途

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: AGENT
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "PBSA", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-TRN-010"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 代理为了加快入住想替学生签约、代收租金，并把申请资料另作营销，可以吗？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 代理不得替住户签租赁/住宿协议或代收押金租金，可协助沟通整理材料。 | required | (SC-TRN-010 §7) |
| C2 | 个人资料只限申请与履约必要范围，不能用于其他目的或向无关方披露。 | required | (SC-TRN-010 §7) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-TRN-010"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-TRN-010 §7 · 7. 代理合规红线</summary>

## 7. 代理合规红线

Safescan 对代理设定明确**合规红线**，覆盖代签、虚假信息、收费违规、隐私与宣传等高风险行为，违反者按第 8 节处罚。**代签（signature fraud）**：代理不得代替住户签押租赁/住宿协议、押金文件或相关表单，不得代作身份核验或代收押金/租金；签约与收款必须由住户本人完成（或以合规电子签署并由住户本人确认），代理仅可协助沟通与材料整理。**虚假信息**：代理不得伪造、夸大或瞒报学生材料、在学证明、资格或申请信息，不得为促成成交而虚报房态、价格或退改条件。

**收费违规**：除协议约定的佣金与可明确的服务费外，代理不得向学生收取任何未经批准的费用（如以"办理费""中介费"名义在住房协议之外额外收费），也不得向学生承诺"Safescan 会退还该费用"。**隐私与宣传**：代理采集、传递或代办的住户个人信息（含护照、签证、监护、健康、联系方式）须按《Privacy Act 1988 (Cth)》与 APPs 执行，仅限申请与履约必要范围，不得用于其他目的或向无关方披露（见 SC-REG-008）；宣传内容须真实、准确、无歧视，不对年龄、国籍、文化、残障等作歧视性表述（见 SC-REG-010）。

代理对 **U18 与国际学生**负有特别注意义务：代理不得对未成年学生作超出监护与校方意见的安排，不得擅自对外披露未成年信息；涉及学生签证、国际学生特殊支持的，应引导至合规渠道而非自行判断。代理不得为获取佣金而向学生施加不当压力（如夸大空房紧张、隐瞒退改成本），也不得通过向 Safescan 员工提供不正当好处来获取优先对待（见 SC-EMP-003）。

</details>

## TC-V2-AGENT-LOOKUP-01 代理代签与信息用途：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: AGENT
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "PBSA", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-TRN-010", "clause": "7", "anchor": "7. 代理合规红线"}]
- **preferred_sources**: ["SC-TRN-010"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-TRN-010 第 7 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 代理不得替住户签租赁/住宿协议或代收押金租金，可协助沟通整理材料。 | required | (SC-TRN-010 §7) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-TRN-010"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-TRN-010 §7 · 7. 代理合规红线</summary>

## 7. 代理合规红线

Safescan 对代理设定明确**合规红线**，覆盖代签、虚假信息、收费违规、隐私与宣传等高风险行为，违反者按第 8 节处罚。**代签（signature fraud）**：代理不得代替住户签押租赁/住宿协议、押金文件或相关表单，不得代作身份核验或代收押金/租金；签约与收款必须由住户本人完成（或以合规电子签署并由住户本人确认），代理仅可协助沟通与材料整理。**虚假信息**：代理不得伪造、夸大或瞒报学生材料、在学证明、资格或申请信息，不得为促成成交而虚报房态、价格或退改条件。

**收费违规**：除协议约定的佣金与可明确的服务费外，代理不得向学生收取任何未经批准的费用（如以"办理费""中介费"名义在住房协议之外额外收费），也不得向学生承诺"Safescan 会退还该费用"。**隐私与宣传**：代理采集、传递或代办的住户个人信息（含护照、签证、监护、健康、联系方式）须按《Privacy Act 1988 (Cth)》与 APPs 执行，仅限申请与履约必要范围，不得用于其他目的或向无关方披露（见 SC-REG-008）；宣传内容须真实、准确、无歧视，不对年龄、国籍、文化、残障等作歧视性表述（见 SC-REG-010）。

代理对 **U18 与国际学生**负有特别注意义务：代理不得对未成年学生作超出监护与校方意见的安排，不得擅自对外披露未成年信息；涉及学生签证、国际学生特殊支持的，应引导至合规渠道而非自行判断。代理不得为获取佣金而向学生施加不当压力（如夸大空房紧张、隐瞒退改成本），也不得通过向 Safescan 员工提供不正当好处来获取优先对待（见 SC-EMP-003）。

</details>

