# COMMISSION-COMPARE：佣金申请与计提支付条件对比

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-COMMISSION-COMPARE-COMPARE-01 佣金申请与计提支付条件对比

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: COMMISSION-COMPARE
- **origin_case_ids**: []
- **test_goal**: cross_document_qa
- **question_type**: ["cross_doc", "process_qa", "boundary"]
- **difficulty**: 难
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-PRD-009", "clause": "6.2", "anchor": "6.2 佣金率与支付条件"}, {"doc_id": "SC-TRN-010", "clause": "3", "anchor": "3. 佣金协议与支付流程"}]
- **preferred_sources**: ["SC-PRD-009"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请比较 SC-PRD-009 第6.2节与 SC-TRN-010 第3节：已经签约到账但还没入住，能否据此直接承诺付款？请区分申请、计提和支付。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | PRD-009 要求有效租约生效、顺利入住及协议条件满足后计提，不在预订或未入住时提前支付。 | required | (SC-PRD-009 §6.2) |
| C2 | TRN-010 允许完成签约且适用款项到账后申请佣金，后续须核对、经理复核、财务按授权周期支付；申请不等于已支付。 | required | (SC-TRN-010 §3) |
| C3 | 两篇表述的流程阶段与条件不同，不能只据签约到账承诺立即支付，应核实具体协议并向财务/授权负责人确认。 | required | (SC-PRD-009 §6.2 AND SC-TRN-010 §3) |

**forbidden_claims**

- 不得编造本轮证据没有提供的数字、个人记录、版本或联系方式。
- 不得将模拟内部政策当作已核验的现行法律。
- 不得引用未交给模型的文档或不支持结论的条款。
- 不得声称已执行申请、审批、付款或系统修改。
- 不得擅自认定任一文档已废止或凭文档编号决定效力。
- 不得把申请佣金等同计提或付款已批准。

**insufficient_evidence_behavior**

仅回答实际证据支持的部分并明确具体缺口，必要时转主管/资料维护人；完整问答缺少必答事实仍不通过。

**pass_criteria**

- 用户明确要求的 required_targets 均须实际取得，完成对比或流程衔接，不能只引用其中一篇。
- 所有 required 事实被正确回答且至少一个完整证据选项实际进入模型上下文。
- 所有关键结论引用真实、适用、获授权的证据；禁止项一票否决。
- preferred_sources 未命中不单独判业务问答失败；新等价证据记 needs_review 后人工复核。

**evidence_review**

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-PRD-009", "SC-TRN-010"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-PRD-009 §6.2 · 6.2 佣金率与支付条件</summary>

### 6.2 佣金率与支付条件

佣金按由代理促成并成功入住的有效租约计算，比例或金额以代理协议约定为准（属内部标准）；佣金仅在租约生效、住户顺利入住且满足协议约定条件后计提，不得在预订或未完成入住时提前支付。计提与支付须有可核对的住户租约与渠道记录，财务部按代理协议与发票/结算单核对后结算，并留存支付凭证。对存在退款、取消或提前离场的租约，公司应按代理协议审查是否调整佣金；凡佣金与未兑现条件挂钩的，应明确调整规则，避免重复支付或超付。

</details>

<details><summary>SC-TRN-010 §3 · 3. 佣金协议与支付流程</summary>

## 3. 佣金协议与支付流程

佣金是代理合作的核心激励，也是本文件风险较高的环节，必须透明、可追溯、且经授权。Safescan 与代理签订**书面佣金协议**，明确佣金计费基础（如按成功签约的租期/床位/房型计算）、佣金比例、结算周期、适用条件（如退租、违约、取消是否影响佣金）、以及否定性条款（如无代理代签不得计佣）。佣金比例、计费基础与否定条件均为 Safescan 内部服务标准，在协议中载明，不得由员工口头承诺超越协议的范围。佣金协议由校企合作与渠道负责人起草、Finance 与合规方会签后方可签署。

佣金支付须以**真实成交与款项到位**为前提：只有当意向住户完成签约、适用的押金/预付款/订金到位（以财务到账为准）后，代理方可申请佣金。支付流程为：代理在系统提交佣金申请并附成交记录 → 租赁顾问核对成交与代理登记 → Property Manager 复核 → Finance 按授权审批与结算周期支付。支付应留痕并进入渠道台账，作为评估、对账与审计依据。凡涉及重复推荐或佣金争议的，由 Property Manager 与 Finance 核对 CRM 线索归属后裁定，避免同一成交被多家代理重复主张。

代理与个人顾问不得私下向 Safescan 员工约定、承诺或支付超越公司政策的报酬、回扣或利益交换，Safescan 员工也不得为谋取个人利益而向代理透露住户信息、优先安排或虚假承诺（见 SC-EMP-003 行为准则与利益冲突）。佣金收入属代理独立经营所得，不构成代理为 Safescan 雇员或享受雇佣法权益；Safescan 通过协议与发票管理支付，保持税务与财务边界清晰（泛引，以相关税法与雇佣法为准）。

</details>

