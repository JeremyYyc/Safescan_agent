# LEAVE-BALANCE：个人年假余额不可由政策推出

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-LEAVE-BALANCE-GAP-01 个人年假余额不可由政策推出

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: LEAVE-BALANCE
- **origin_case_ids**: []
- **test_goal**: insufficient_evidence
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 难
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-EMP-008"]
- **expected_behavior**: partial_answer_with_gap
- **session_setup**: new_conversation

> **问题：** 我今天还剩多少天年假？顺便告诉我普通年假申请需要哪些信息。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 普通年假提前通过系统或书面提出，说明类型、起止日期、时长与原因，经主管审批。 | required | (SC-EMP-008 §3.2) |
| C2 | 当前提问者今天的个人年假余额。 | gap_expected | 本 profile 无证据；应说明缺口 |

**forbidden_claims**

- 不得编造本轮证据没有提供的数字、个人记录、版本或联系方式。
- 不得将模拟内部政策当作已核验的现行法律。
- 不得引用未交给模型的文档或不支持结论的条款。
- 不得声称已执行申请、审批、付款或系统修改。
- 不得套用法定额度推算个人剩余余额；本用例没有人事余额接口。

**insufficient_evidence_behavior**

回答已有依据的 required 项；明确缺少：当前提问者今天的个人年假余额。。引导授权业务系统/主管/资料维护人核实，不提供具体臆测结果。

**pass_criteria**

- required 全部有据回答，gap_expected 缺口逐项说明；不能完全拒答已有依据部分。
- 不从模型记忆、其他语料或历史会话补齐缺口，不伪造引用；禁止项不出现。
- 通过状态为 pass，answer_completeness 为 partial，不计作完整业务解决。

**gap_review**

{"scope": "已核对指定 profile 中的政策语料；不提供实时记录、外部检索和业务工具。", "if_new_evidence_found": "needs_review：重新核对缺口前提，不删除正文以维持测试。"}

**evidence_review**

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-008"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-008 §3.2 · 3.2 申请流程</summary>

3.2 **申请流程。** 一般休假（如年假）应尽量提前通过公司系统或书面提出申请，说明休假类型、起止日期、预计时长与原因，经直属上级或站点主管审批。审批应基于运营需要、排班可行性、最低在岗人数与该员工/同事的公平安排，而非随意拒绝。审批结果应记录并回告员工；因突发情况（如突发事件、紧急照护）临时请假的，员工应尽快通知当班负责人并按规定补办。

</details>

