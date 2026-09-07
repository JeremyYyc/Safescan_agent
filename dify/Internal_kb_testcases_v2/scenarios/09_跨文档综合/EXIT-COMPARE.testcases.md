# EXIT-COMPARE：离职业务交接与 IT 回收

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-EXIT-COMPARE-COMPARE-01 离职业务交接与 IT 回收

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: EXIT-COMPARE
- **origin_case_ids**: []
- **test_goal**: cross_document_qa
- **question_type**: ["cross_doc", "process_qa", "boundary"]
- **difficulty**: 难
- **corpus_profile**: emp_only
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-EMP-009", "clause": "9.4", "anchor": "9.4 交接清单"}, {"doc_id": "SC-EMP-006", "clause": "9.3", "anchor": "9.3 离职的信息回收"}]
- **preferred_sources**: ["SC-EMP-009"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请对照 SC-EMP-009 第9.4条和 SC-EMP-006 第9.3条：离职业务交接与系统回收分别要做什么，做完交接能保留住户副本吗？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 业务交接清单包括未完成工作、租约工单投诉跟进、物品设备、账号及敏感资料，由主管或接任人监督。 | required | (SC-EMP-009 §9.4) |
| C2 | IT/HR/站点回收系统及远程访问，禁止离职保留数据副本，保密义务持续。 | required | (SC-EMP-006 §9.3) |

**forbidden_claims**

- 不得编造本轮证据没有提供的数字、个人记录、版本或联系方式。
- 不得将模拟内部政策当作已核验的现行法律。
- 不得引用未交给模型的文档或不支持结论的条款。
- 不得声称已执行申请、审批、付款或系统修改。

**insufficient_evidence_behavior**

仅回答实际证据支持的部分并明确具体缺口，必要时转主管/资料维护人；完整问答缺少必答事实仍不通过。

**pass_criteria**

- 用户明确要求的 required_targets 均须实际取得，完成对比或流程衔接，不能只引用其中一篇。
- 所有 required 事实被正确回答且至少一个完整证据选项实际进入模型上下文。
- 所有关键结论引用真实、适用、获授权的证据；禁止项一票否决。
- preferred_sources 未命中不单独判业务问答失败；新等价证据记 needs_review 后人工复核。

**evidence_review**

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-EMP-009", "SC-EMP-006"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-EMP-009 §9.4 · 9.4 交接清单</summary>

9.4 **交接清单。** 离职员工的交接应通过交接清单进行，覆盖：未完成的工作与项目、在职住户/租约/工单/投诉的状态与跟进、钥匙/门禁卡/对讲机/制服等物品、设备与资产、系统与账号权限、以及任何涉密或敏感资料。交接应由直属上级或其指定的接任者监督，确保工作无缝衔接且无信息断链。对重要岗位，应安排足够时间的交接期并做好书面交接记录。

</details>

<details><summary>SC-EMP-006 §9.3 · 9.3 离职的信息回收</summary>

9.3 **离职的信息回收。** 员工离职时，由 IT 与 HR/站点协调完成信息权限回收：立即停用系统账号、邮箱与 VPN，回收门禁卡与钥匙，收回公司设备与可移动介质，并取消远程访问。员工的最后工作日应完成交接，将持有的住户与业务数据交接给指定接任者，禁止在离职后保留任何副本。离职后，员工对在职期间获知的保密信息仍负有持续保密义务，本政策中的保密义务不因劳动关系结束而终止。（本政策应与 SC-EMP-009 离职流程联动执行。）

</details>

