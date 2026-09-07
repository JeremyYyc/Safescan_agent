# Safescan RAG 测试集 v2

本目录按 [测试规范 v2.0](../../kb_build/testcase_spec.md) 编写，与旧 `Internal_kb_testcases/` 并列，遵循本次用户要求的同级目录组织方式。知识正文、旧用例、旧清单与旧校验脚本保持不变。

已设计 **66 条用例、38 个场景**，全部为开发验证用例，尚未在 Dify 执行。覆盖八类业务主题，正向事实证据涉及 **24/93 篇文档**，包含全部 **9/9 篇 EMP**；不是把旧 279 条全部迁移，也不宣称 93 篇逐篇覆盖。未覆盖文档完整列在 [coverage.json](coverage.json)。

## 测试类型与适用语料

| 目标 | 数量 | 通过标准 |
|---|---:|---|
| document_lookup | 27 | 用户明确指定文档/条款，目标必须命中 |
| business_qa | 27 | 必答事实逐项有据，不绑定唯一文件 |
| cross_document_qa | 4 | 取得明确指定的两份资料并完成对比/衔接 |
| insufficient_evidence | 4 | 回答已知部分、明确缺口，不凭记忆补齐 |
| access_boundary | 4 | 未授权身份拿不到员工库切片、上下文或引用 |

- `emp_only`：32 条，当前 EMP 九篇原型的候选执行集。其中 4 条权限测试需要受控身份夹具支持，不能通过聊天文本或随意填写角色来模拟真实授权。
- `internal_full`：34 条，需先接入相应全库配置。本地有 93 篇不等于线上已经索引。
- 全部属于开发集；这些带公开答案的文件不能冒充独立盲测集。后续冻结参数后另建未用于调参的场景/问法验收集。

## 文件导航

| 文件 | 用途 |
|---|---|
| [scenarios/](scenarios/) | 按业务场景查看问题、身份、事实、AND/OR 证据、禁止项、验收标准和源文摘录 |
| [emp_only_questions.csv](emp_only_questions.csv) | 筛出的 32 条 EMP 测试问题，方便逐行复制到 Dify |
| [questions.csv](questions.csv) | 全部 66 条问题的简表 |
| [manifest.v2.jsonl](manifest.v2.jsonl) | 完整结构化字段，保留 claims 与嵌套证据选项，不压平成唯一 expected_docs |
| [profiles/emp_only.json](profiles/emp_only.json) | EMP 九篇的本地版本、内容哈希及待绑定 Dify 信息 |
| [profiles/internal_full.json](profiles/internal_full.json) | 全部 93 篇的本地快照及待绑定 Dify 信息 |
| [coverage.json](coverage.json) | 文档覆盖和用例映射，含未覆盖清单 |
| [run_record.template.json](run_record.template.json) | 单次执行和人工评分记录模板；不是已执行结果 |
| [scripts/build_suite.py](scripts/build_suite.py) | 人工编写的用例定义与派生文件生成器 |
| [scripts/validate_suite.py](scripts/validate_suite.py) | 只读静态检查，不调用 Dify、不判断答案语义 |

CSV 是人工执行简表，不声称能直接导入任意 Dify 版本的批量测试功能。参考断言在对应场景 Markdown 和完整 JSONL 中，不能只看 CSV 判断通过。

## 当前 EMP 原型的推荐执行顺序

先对照 [profiles/emp_only.json](profiles/emp_only.json) 确认上传版本，再用 `staff_amy` 受控模拟员工身份，新建会话逐条运行。下面路径都只需要 EMP 九篇：

| 顺序 | case_id | 重点 |
|---|---|---|
| 1 | TC-V2-EAP-QA-01 | 保密原则与例外，不能绝对化 |
| 2 | TC-V2-NIGHT-GENERAL-QA-01 | 夜班报备与冲突处理 |
| 3 | TC-V2-NIGHT-SOLO-GAP-01 | 原独岗问题只能局部回答，不引用 SOP-003 |
| 4 | TC-V2-DATA-ACCESS-QA-01 | 内部角色不等于任意访问个人记录 |
| 5 | TC-V2-CONFLICT-QA-01 | 亲属供应商申报和回避 |
| 6 | TC-V2-PAYSLIP-QA-01 | 内部反馈时限不等于权利失效 |
| 7 | TC-V2-EXIT-COMPARE-COMPARE-01 | 两份员工文档的交接与权限回收衔接 |
| 8 | TC-V2-LEAVE-BALANCE-GAP-01 | 能答申请政策，不能编个人余额 |
| 9 | TC-V2-EAP-CONTACT-GAP-01 | 无据的电话和免费次数不能补齐 |
| 10 | TC-V2-EMPLOYMENT-LOOKUP-01 | 明确文档定位，不能用其他来源替代 |

随后运行 CSV 中其余 EMP 用例。四个未授权身份测试要先由服务端或受控测试夹具注入身份、固定 `allowed_kbs=[]`；当前下拉框不支持的身份记 `not_applicable`，不是 `pass`。先运行对应正向员工对照，确认知识库仍启用；不能禁用全库来获得拒绝成功。

完整知识库接入后再执行 `internal_full`。尤其对比 [独岗场景](scenarios/02_夜班与现场操作/NIGHT-SOLO.testcases.md) 的全库问答、指定手册定位与 EMP 缺口三种结果。同一问题在不同 profile 下不能共用一套通过条件。

## 运行前准备

1. 语料配置已经包含真实本地文档 ID、版本、SHA-256 和内容快照 ID。Dify 的库/文档 ID、索引和启用状态为 `null`，因为尚未检查你的线上配置，执行前必须核实并填写。
2. `staff_internal` 是逻辑库名；如果线上按主题拆库，映射为当前 profile 所需的全部实际 dataset ID，不能遗漏或混入其他语料。模拟员工在本轮可读取整个 profile 是测试假设，不代表生产岗位授权已经完成。
3. 复制运行记录模板，为每次运行填写实际模型、应用/提示词版本、切片、Top K、阈值、rerank、过滤及身份。模板 Top K=5 只是起始建议，最终以记录的实际值为准。
4. 每条新建会话。资料不足用例不接业务余额、房态或联网工具；若增加工具，必须另建测试条件，不能沿用旧缺口预期。
5. 保存检索结果及真正交给模型的上下文、回答、引用。没有运行日志时不能宣称权限通过。执行失败与无结果分开记录。
6. 不上传本测试集、证据摘录、manifest 或答案到被测知识库。

## 怎样评分

- 每个 `required` 事实都必须满足；`evidence_options` 之间是 OR，选项中的 `all_of` 是 AND。
- `preferred_sources` 未命中不单独判业务问答失败。替代证据须适用且实际进入模型上下文；新发现的未列证据先 `needs_review`，人工核对后统一更新与复评。
- 定位和明确比较问题的 `required_targets` 是硬条件。自然业务问答无硬性文档目标。
- `gap_expected` 是固定语料中的缺口：有据回答其他必答项、明确缺口才通过。结果可为 `pass + partial`，不能统计成完整业务解决。
- 权限用例使用 `authorization_assertions`，不是把系统授权规则伪装成文档事实；普通政策问答则使用 claims。
- 任何无据补充、错误关键引用、越权或禁止项都不能用平均分抵消。
- 分组记录定位、证据/回答覆盖、依据一致性、引用、缺口及权限。状态为 pass / fail / needs_review / not_applicable / execution_error；尚未执行保留 not_run。

佣金对比用例区分“申请、计提、支付”的表述，不能因为不同就擅自宣布某文件失效，也不能只据签约到账承诺支付。遇到未能消解的适用条件，应说明并核实协议与授权负责人。

## 维护与检查

从项目根目录执行静态检查：

```sh
python3 dify/Internal_kb_testcases_v2/scripts/validate_suite.py
```

检查字段、唯一 ID、旧编号关联、来源存在、profile 范围、本地哈希、证据摘录和场景文件。`STATIC PASS` 不代表事实语义或 Dify 在线测试通过。

需要修改问题/事实时，编辑 `scripts/build_suite.py` 中人工用例定义，再生成派生文件：

```sh
python3 dify/Internal_kb_testcases_v2/scripts/build_suite.py
python3 dify/Internal_kb_testcases_v2/scripts/validate_suite.py
```

生成会覆盖本目录的 Markdown、JSONL、CSV、coverage、profiles 与模板，且 profiles 的线上绑定会重新置为未核实。请把已完成绑定和运行记录复制到另一个运行目录保存，再重建；不要只改单份派生 Markdown 而让清单失步。生成器不修改知识正文或旧测试资产。

当前静态校验只确认材料结构和引用存在；事实语义已按选定条款编写，但候选替代来源未穷尽全库，后续以人工复核扩充。旧 `qa_testcases.py` 不读取这个新目录，继续服务旧测试集。
