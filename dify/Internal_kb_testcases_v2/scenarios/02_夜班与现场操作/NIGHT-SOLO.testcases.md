# NIGHT-SOLO：独岗完整业务问题

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-NIGHT-SOLO-QA-01 独岗完整业务问题

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: NIGHT-SOLO
- **origin_case_ids**: ["TC-SC-SOP-003-01"]
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-SOP-003"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 我一个人上夜班，公司对“独岗”有什么安全要求？进住户房间或处理冲突时要注意什么？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 独岗时保持可联系并清楚应急呼叫和升级渠道。 | required | (SC-SOP-003 §3.4) OR (SC-EMP-007 §6.1 AND SC-EMP-007 §6.3) |
| C2 | 进房等场景优先结伴或保安陪同，避免独自进入高风险或密闭空间。 | required | (SC-SOP-003 §3.4) |
| C3 | 处理冲突时避免独自冒险，呼叫支援。 | required | (SC-SOP-003 §3.4) OR (SC-EMP-007 §6.5) OR (SC-EMP-004 §5.2) |
| C4 | 随身携带通讯工具与夜班袋。 | optional | (SC-SOP-003 §3.4) |

**forbidden_claims**

- 不得编造本轮证据没有提供的数字、个人记录、版本或联系方式。
- 不得将模拟内部政策当作已核验的现行法律。
- 不得引用未交给模型的文档或不支持结论的条款。
- 不得声称已执行申请、审批、付款或系统修改。
- 不得把陪同当成法律进房授权。

**insufficient_evidence_behavior**

仅回答实际证据支持的部分并明确具体缺口，必要时转主管/资料维护人；完整问答缺少必答事实仍不通过。

**pass_criteria**

- 所有 required 事实被正确回答且至少一个完整证据选项实际进入模型上下文。
- 所有关键结论引用真实、适用、获授权的证据；禁止项一票否决。
- preferred_sources 未命中不单独判业务问答失败；新等价证据记 needs_review 后人工复核。

**evidence_review**

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-SOP-003", "SC-EMP-007", "SC-EMP-004"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-SOP-003 §3.4 · 3.4 独岗安全原则</summary>

**3.4 独岗安全原则。** 夜班经理在独岗情况下应遵守以下安全原则：始终与外部保持可联系状态，熟悉呼叫链并随身携带通讯工具与夜班袋；凡需进入住户房间、公共区或独处场景，应优先结伴或由保安陪同，避免单人进入高风险或密闭空间；涉及人身安全、冲突或潜在犯罪时，立即呼叫支援而非独自介入；遇到无法确认安全的情形，宁可按"最坏情形"呼叫求援，也不因怕麻烦而省略。
独岗安全是本文档最核心的原则，夜班经理应把"先保全自己"视为对住户与公司负责的必要前提。

</details>

<details><summary>SC-EMP-007 §6.1 · 6.1 双人报备</summary>

6.1 **双人报备。** 夜班与单兵岗位应实行"报备"制度，即值守员工在上班、下班以及关键时间点向指定的值班负责人或系统进行报备，以确认其在岗且安全。报备的方式可为定时打卡、系统签到、与当班调度确认等。若员工未能按时报备且无法联答，站点应按约定的失联处理流程启动核查，防止单兵值守人员发生意外而无人知晓。

</details>

<details><summary>SC-EMP-007 §6.3 · 6.3 应急呼叫链</summary>

6.3 **应急呼叫链。** 夜班与单兵岗位必须明确应急呼叫链，即：遇到火警、医疗急症、人身安全威胁、重大秩序事件或设备事故时，夜班员工应第一时间呼叫谁、按什么顺序升级、通过什么渠道（对讲、电话、系统、报警）。呼叫链应挂载于站点应急手册并在夜班员工入职与复训时确认其知晓。凡涉及执法、救护或消防机构的，按"第一时间联系机构而非自行判断"的纪律处理（见 kb_build/02 法规基线 B 节）。

</details>

<details><summary>SC-EMP-007 §6.5 · 6.5 通勤与人身安全提示</summary>

6.5 **通勤与人身安全提示。** 夜班员工在深夜通勤时应有相应的安全安排，如由站点协助安排安全的交通方式、结伴或报备到达，避免在僻静路段独自步行。夜间处理住户冲突、醉酒或情绪激动事件时，员工应保持安全距离、避免独处处理，必要时呼叫支援或联系保安/警方。夜班员工的人身安全与住户的人身安全同等重要，任何情况下都不应让值守人员冒险单独处置高风险事件。

</details>

<details><summary>SC-EMP-004 §5.2 · 5.2 旁观者的边界</summary>

5.2 **旁观者的边界。** 主动介入要以人身安全为前提，避免激化冲突或让自己陷入危险。在面对可能升级为暴力或严重冲突的场景时，应优先求助主管、安保或紧急服务（如需），而非贸然介入。旁观者上报的信息应客观真实，不得添油加醋或传播未经证实的细节。

</details>

## TC-V2-NIGHT-SOLO-LOOKUP-01 独岗指定手册定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: NIGHT-SOLO
- **origin_case_ids**: ["TC-SC-SOP-003-01"]
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-SOP-003", "clause": "3.4", "anchor": "3.4 独岗安全原则"}]
- **preferred_sources**: ["SC-SOP-003"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请查找 SC-SOP-003 第 3.4 条独岗安全原则，并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 保持联系熟悉呼叫链并携带通讯工具与夜班袋；进房优先结伴，避免独自进入高风险密闭空间；冲突立即求援。 | required | (SC-SOP-003 §3.4) |

**forbidden_claims**

- 不得编造本轮证据没有提供的数字、个人记录、版本或联系方式。
- 不得将模拟内部政策当作已核验的现行法律。
- 不得引用未交给模型的文档或不支持结论的条款。
- 不得声称已执行申请、审批、付款或系统修改。

**insufficient_evidence_behavior**

仅回答实际证据支持的部分并明确具体缺口，必要时转主管/资料维护人；完整问答缺少必答事实仍不通过。

**pass_criteria**

- SOP-003 §3.4 必须命中且实际传给模型；正确概括指定要求，禁止项不出现。

**evidence_review**

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-SOP-003"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-SOP-003 §3.4 · 3.4 独岗安全原则</summary>

**3.4 独岗安全原则。** 夜班经理在独岗情况下应遵守以下安全原则：始终与外部保持可联系状态，熟悉呼叫链并随身携带通讯工具与夜班袋；凡需进入住户房间、公共区或独处场景，应优先结伴或由保安陪同，避免单人进入高风险或密闭空间；涉及人身安全、冲突或潜在犯罪时，立即呼叫支援而非独自介入；遇到无法确认安全的情形，宁可按"最坏情形"呼叫求援，也不因怕麻烦而省略。
独岗安全是本文档最核心的原则，夜班经理应把"先保全自己"视为对住户与公司负责的必要前提。

</details>

## TC-V2-NIGHT-SOLO-GAP-01 仅 EMP 的独岗资料缺口

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: NIGHT-SOLO
- **origin_case_ids**: ["TC-SC-SOP-003-01"]
- **test_goal**: insufficient_evidence
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 难
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-EMP-007"]
- **expected_behavior**: partial_answer_with_gap
- **session_setup**: new_conversation

> **问题：** 我一个人上夜班，公司对“独岗”有什么安全要求？进住户房间或处理冲突时要注意什么？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 独岗时保持可联系并清楚应急呼叫和升级渠道。 | required | (SC-EMP-007 §6.1 AND SC-EMP-007 §6.3) |
| C2 | 处理冲突时避免独自冒险，呼叫支援。 | required | (SC-EMP-007 §6.5) OR (SC-EMP-004 §5.2) |
| C3 | 进房等场景优先结伴或保安陪同，避免独自进入高风险或密闭空间。 | gap_expected | 本 profile 无证据；应说明缺口 |

**forbidden_claims**

- 不得编造本轮证据没有提供的数字、个人记录、版本或联系方式。
- 不得将模拟内部政策当作已核验的现行法律。
- 不得引用未交给模型的文档或不支持结论的条款。
- 不得声称已执行申请、审批、付款或系统修改。
- 不得引用未接入的 SOP-003 或以 EMP-006 证明进房陪同要求。
- 不得无据补充夜班袋清单。

**insufficient_evidence_behavior**

回答已有依据的 required 项；明确缺少：进房等场景优先结伴或保安陪同，避免独自进入高风险或密闭空间。。引导授权业务系统/主管/资料维护人核实，不提供具体臆测结果。

**pass_criteria**

- required 全部有据回答，gap_expected 缺口逐项说明；不能完全拒答已有依据部分。
- 不从模型记忆、其他语料或历史会话补齐缺口，不伪造引用；禁止项不出现。
- 通过状态为 pass，answer_completeness 为 partial，不计作完整业务解决。

**gap_review**

{"scope": "已核对指定 profile 中的政策语料；不提供实时记录、外部检索和业务工具。", "if_new_evidence_found": "needs_review：重新核对缺口前提，不删除正文以维持测试。"}

**evidence_review**

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-007", "SC-EMP-004"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-007 §6.1 · 6.1 双人报备</summary>

6.1 **双人报备。** 夜班与单兵岗位应实行"报备"制度，即值守员工在上班、下班以及关键时间点向指定的值班负责人或系统进行报备，以确认其在岗且安全。报备的方式可为定时打卡、系统签到、与当班调度确认等。若员工未能按时报备且无法联答，站点应按约定的失联处理流程启动核查，防止单兵值守人员发生意外而无人知晓。

</details>

<details><summary>SC-EMP-007 §6.3 · 6.3 应急呼叫链</summary>

6.3 **应急呼叫链。** 夜班与单兵岗位必须明确应急呼叫链，即：遇到火警、医疗急症、人身安全威胁、重大秩序事件或设备事故时，夜班员工应第一时间呼叫谁、按什么顺序升级、通过什么渠道（对讲、电话、系统、报警）。呼叫链应挂载于站点应急手册并在夜班员工入职与复训时确认其知晓。凡涉及执法、救护或消防机构的，按"第一时间联系机构而非自行判断"的纪律处理（见 kb_build/02 法规基线 B 节）。

</details>

<details><summary>SC-EMP-007 §6.5 · 6.5 通勤与人身安全提示</summary>

6.5 **通勤与人身安全提示。** 夜班员工在深夜通勤时应有相应的安全安排，如由站点协助安排安全的交通方式、结伴或报备到达，避免在僻静路段独自步行。夜间处理住户冲突、醉酒或情绪激动事件时，员工应保持安全距离、避免独处处理，必要时呼叫支援或联系保安/警方。夜班员工的人身安全与住户的人身安全同等重要，任何情况下都不应让值守人员冒险单独处置高风险事件。

</details>

<details><summary>SC-EMP-004 §5.2 · 5.2 旁观者的边界</summary>

5.2 **旁观者的边界。** 主动介入要以人身安全为前提，避免激化冲突或让自己陷入危险。在面对可能升级为暴力或严重冲突的场景时，应优先求助主管、安保或紧急服务（如需），而非贸然介入。旁观者上报的信息应客观真实，不得添油加醋或传播未经证实的细节。

</details>

