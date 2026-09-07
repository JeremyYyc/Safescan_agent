# ADVERTISING：宣传真实与优惠披露

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-ADVERTISING-QA-01 宣传真实与优惠披露

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: ADVERTISING
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-PRD-009"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 为了促成预订，能不能写未经核实的“仅剩三套”“限时立省”？优惠广告应披露什么？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 剩余房源和限时优惠须有可核实事实，不制造虚假紧迫感。 | required | (SC-PRD-009 §7.1) |
| C2 | 披露适用条件、活动期与金额，不误导原价或立省，不作违背活动规则/租约的口头承诺。 | required | (SC-PRD-009 §7.2) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-PRD-009"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-PRD-009 §7.1 · 7.1 真实房源信息</summary>

### 7.1 真实房源信息

所有对外宣传（房源页、社交媒体、随房宣传、代理材料）应真实、准确、及时，不得使用过期或与在租房源不符的照片、面积、价格或设施描述。房型、价格、可入住时间、公共设施等服务承诺应与实际一致，避免为吸引咨询而夸大或虚构条件。涉及"剩余房源有限""限时优惠"等表述，须以可核实的事实为依据，不得制造虚假紧迫感；市场团队负责定期复核在租信息，确保与系统房态一致。

</details>

<details><summary>SC-PRD-009 §7.2 · 7.2 消费者法与广告合规提示</summary>

### 7.2 消费者法与广告合规提示

Safescan 的市场与宣传应符合澳大利亚消费者法（ACL）关于误导性行为、虚假陈述与不实广告的规定（泛引 ACL，具体要求以现行消费者法为准）。促销与优惠广告应明确适用条件、活动期与金额，且不得以误导性方式呈现"原价""立省"等。员工与代理在向潜在住户说明价格或权益时，不得作出与活动规则或租约不符的口头承诺；凡发现可能构成误导的内容，应立即更正并从相关渠道撤回，必要时上报合规部。

</details>

## TC-V2-ADVERTISING-LOOKUP-01 宣传真实与优惠披露：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: ADVERTISING
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-PRD-009", "clause": "7.1", "anchor": "7.1 真实房源信息"}]
- **preferred_sources**: ["SC-PRD-009"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-PRD-009 第 7.1 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 剩余房源和限时优惠须有可核实事实，不制造虚假紧迫感。 | required | (SC-PRD-009 §7.1) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-PRD-009"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-PRD-009 §7.1 · 7.1 真实房源信息</summary>

### 7.1 真实房源信息

所有对外宣传（房源页、社交媒体、随房宣传、代理材料）应真实、准确、及时，不得使用过期或与在租房源不符的照片、面积、价格或设施描述。房型、价格、可入住时间、公共设施等服务承诺应与实际一致，避免为吸引咨询而夸大或虚构条件。涉及"剩余房源有限""限时优惠"等表述，须以可核实的事实为依据，不得制造虚假紧迫感；市场团队负责定期复核在租信息，确保与系统房态一致。

</details>

