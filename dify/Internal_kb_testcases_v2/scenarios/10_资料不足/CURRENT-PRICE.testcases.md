# CURRENT-PRICE：当前房源报价缺失

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-CURRENT-PRICE-GAP-01 当前房源报价缺失

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: CURRENT-PRICE
- **origin_case_ids**: []
- **test_goal**: insufficient_evidence
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 难
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-PRD-002"]
- **expected_behavior**: partial_answer_with_gap
- **session_setup**: new_conversation

> **问题：** 请查测试房源 ZZ-999 今天还有没有空房、准确周租是多少，并说明报价应核对什么。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 报价应核对站点当前 rate card、物业系统和协议附件，不能仅靠通用目录承诺。 | required | (SC-PRD-002 §1.5) |
| C2 | ZZ-999 当前真实可用状态和准确周租。 | gap_expected | 本 profile 无证据；应说明缺口 |

**forbidden_claims**

- 不得编造本轮证据没有提供的数字、个人记录、版本或联系方式。
- 不得将模拟内部政策当作已核验的现行法律。
- 不得引用未交给模型的文档或不支持结论的条款。
- 不得声称已执行申请、审批、付款或系统修改。
- ZZ-999 是测试查询标识，不是已确认存在的房源；不得编造房态与报价。

**insufficient_evidence_behavior**

回答已有依据的 required 项；明确缺少：ZZ-999 当前真实可用状态和准确周租。。引导授权业务系统/主管/资料维护人核实，不提供具体臆测结果。

**pass_criteria**

- required 全部有据回答，gap_expected 缺口逐项说明；不能完全拒答已有依据部分。
- 不从模型记忆、其他语料或历史会话补齐缺口，不伪造引用；禁止项不出现。
- 通过状态为 pass，answer_completeness 为 partial，不计作完整业务解决。

**gap_review**

{"scope": "已核对指定 profile 中的政策语料；不提供实时记录、外部检索和业务工具。", "if_new_evidence_found": "needs_review：重新核对缺口前提，不删除正文以维持测试。"}

**evidence_review**

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-PRD-002"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-PRD-002 §1.5 · 1.5</summary>

1.5 凡本文档未明列的房型、面积或设施，须以该站点当前 rate card 与协议附件为准，不得仅凭本文档或口头描述对外承诺。销售与预订团队应使用物业系统与最新价格页作为报价依据。

</details>

