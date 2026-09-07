# MINIMIZE：住户信息采集

> 开发验证用例；所有问题均未在 Dify 执行。勿上传本文件到知识库。

## TC-V2-MINIMIZE-QA-01 住户信息采集

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: MINIMIZE
- **origin_case_ids**: []
- **test_goal**: business_qa
- **question_type**: ["policy_qa", "boundary"]
- **difficulty**: 中
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: []
- **preferred_sources**: ["SC-LGL-010"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 为了以后营销方便，签约时能顺便多收一些无关的住户信息吗？

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 只收与既定业务目的直接相关且必要的信息，不能以备用或以后可能用到为由超范围采集。 | required | (SC-LGL-010 §4) OR (SC-EMP-006 §3.2) OR (SC-REG-008 §3.5) |
| C2 | 可通过去标识、匿名或聚合实现目的时优先采用，敏感信息另行评估必要性与更严格依据。 | required | (SC-LGL-010 §4) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-LGL-010", "SC-EMP-006", "SC-REG-008"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-LGL-010 §4 · 4. 数据收集清单与最小化原则</summary>

## 4. 数据收集清单与最小化原则

Safescan 只采集为达成租赁/住宿、管理、安全与法律义务所必需的个人信息。信息采集范围应结合租约与业务需要、并依法定要求，遵循"仅采集必要信息"的最小化原则。以下为 Safescan 通常采集的信息（**内部清单**，实际以各站点赞同告知书所列为准）：

- **身份与联系**：姓名、出生日期、联系方式（电话/邮箱）、紧急联系人。用于身份核验与日常联系。
- **财务与押金**：付款方式、押金（Bond）记录、支付记录、可能的信用/身份文件。用于租金、押金与追索管理（见 SC-LGL-003、SC-LGL-006）。
- **居住与设备**：入住人数、宠物、车辆、房间与门禁信息。用于居住管理、安全与设施。
- **影像与门禁**：可识别个人的 CCTV 影像、门禁刷卡记录。用于安全与楼宇运营（见第 9 节）。
- **学生线附加**：就读学校、课程/学期、学校联系人、必要时学籍/签证信息（用于住宿资格与福祉支持，见 SC-LGL-011）。

**最小化要求**：员工在采集时须逐项判断"是否必要、是否与既定目的直接相关"，避免收集与租赁无关的过度信息。凡能通过去标识化、匿名化或改以聚合方式达成的目的，应优先采用；不得以"备用""以后可能用到"为由超范围采集。对敏感信息（见第 5 节）更须单独评估必要性并取得更严格处理依据，不得与常规信息一并任意采集。

</details>

<details><summary>SC-EMP-006 §3.2 · 3.2 最小化收集原则</summary>

3.2 **最小化收集原则。** 我们只收集完成合法业务目的所必需的最少信息，不因"以后可能用到"而超额收集。例如，销售与预订仅收集完成租约/住宿协议所需的信息（身份、联系方式、签证/在读核验、紧急联系人），不收集与居住无直接关系的政治观点、宗教或性取向信息。员工应在确有必要时才向住户索取敏感信息（如健康或无障碍需求），并单独说明目的。

</details>

<details><summary>SC-REG-008 §3.5 · 3.5 目的限制与最小必要</summary>

3.5 **目的限制与最小必要**：收集信息必须以明确、合法、与业务直接相关的目的为限；并在实现目的所需范围内尽量少收集。前台、安保、IT、物业各岗位不得出于好奇或"以防万一"收集超出目的的信息。

</details>

## TC-V2-MINIMIZE-LOOKUP-01 住户信息采集：指定条款定位

- **spec_version**: 2.0
- **case_version**: 1.0
- **scenario_id**: MINIMIZE
- **origin_case_ids**: []
- **test_goal**: document_lookup
- **question_type**: ["retrieval"]
- **difficulty**: 易
- **corpus_profile**: internal_full
- **user_context**: {"fixture_id": "staff_amy", "user_role": "property_manager", "identity_source": "受控测试夹具；线上必须映射服务端身份", "allowed_kbs": ["staff_internal"], "state": "NSW", "business_line": "GR", "property": "not_applicable"}
- **required_targets**: [{"doc_id": "SC-LGL-010", "clause": "4", "anchor": "4. 数据收集清单与最小化原则"}]
- **preferred_sources**: ["SC-LGL-010"]
- **expected_behavior**: complete_answer
- **session_setup**: new_conversation

> **问题：** 请定位 SC-LGL-010 第 4 条/节 并概括其要求。

| claim_id | 必答事实 | requirement | 证据选项（OR；组内 AND） |
|---|---|---|---|
| C1 | 只收与既定业务目的直接相关且必要的信息，不能以备用或以后可能用到为由超范围采集。 | required | (SC-LGL-010 §4) |

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

{"method": "逐条核对原文；静态脚本只验证引用存在，不代替语义审核", "reviewed_doc_ids": ["SC-LGL-010"], "exhaustive": false, "unlisted_source_policy": "发现新充分来源先 needs_review；更新标注后同批一致复评。"}

**证据审核摘录（只供测试人员）**

<details><summary>SC-LGL-010 §4 · 4. 数据收集清单与最小化原则</summary>

## 4. 数据收集清单与最小化原则

Safescan 只采集为达成租赁/住宿、管理、安全与法律义务所必需的个人信息。信息采集范围应结合租约与业务需要、并依法定要求，遵循"仅采集必要信息"的最小化原则。以下为 Safescan 通常采集的信息（**内部清单**，实际以各站点赞同告知书所列为准）：

- **身份与联系**：姓名、出生日期、联系方式（电话/邮箱）、紧急联系人。用于身份核验与日常联系。
- **财务与押金**：付款方式、押金（Bond）记录、支付记录、可能的信用/身份文件。用于租金、押金与追索管理（见 SC-LGL-003、SC-LGL-006）。
- **居住与设备**：入住人数、宠物、车辆、房间与门禁信息。用于居住管理、安全与设施。
- **影像与门禁**：可识别个人的 CCTV 影像、门禁刷卡记录。用于安全与楼宇运营（见第 9 节）。
- **学生线附加**：就读学校、课程/学期、学校联系人、必要时学籍/签证信息（用于住宿资格与福祉支持，见 SC-LGL-011）。

**最小化要求**：员工在采集时须逐项判断"是否必要、是否与既定目的直接相关"，避免收集与租赁无关的过度信息。凡能通过去标识化、匿名化或改以聚合方式达成的目的，应优先采用；不得以"备用""以后可能用到"为由超范围采集。对敏感信息（见第 5 节）更须单独评估必要性并取得更严格处理依据，不得与常规信息一并任意采集。

</details>

