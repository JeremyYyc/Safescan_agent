# 澳大利亚租房/学生公寓公司内部文档体系调研
## 适用对象：Scape / Student One / UniLodge / Meriton（用户确认 "Milton" = Meriton）
### 用途：为面向这类公司的"员工侧 Agentic Workflow + RAG 知识库"提供文档类型与内容结构参考

> 取证范围说明：真正的**内部员工手册**不公开。本文的"有实据"内容来自各公司公开的住户端/合作方文档（条款、手册、流程页、FAQ、应急计划等，均已下载原文或核实原文片段，见文末来源表）；"推断/行业标准做法"内容（企业内部 SOP、培训手册、岗位手册等）已明确标注，仅作为文档分类设计的合理假设，具体条款切勿直接当作真实条款使用。

---

## 1. 四家公司定位速览

| 公司 | 定位 | 业态 | 主要区域 | 对应法规底色 |
|---|---|---|---|---|
| **Scape**（Scape Australia） | 澳洲大型**学生公寓(PBSA)**开发商+运营商 | 整栋全家具学生公寓，按房/床位出租 | 悉尼、墨尔本、布里斯班、阿德莱德、珀斯等 | 与住户签**州法下的 Residential Tenancy Agreement**，另有一套 Booking T&C（按 NSW/QLD/VIC/SA 分条款） |
| **Student One** | 布里斯班市中心学生公寓品牌（据公开报道 2019 年被 Scape/黑石合资体收购） | 三栋全家具学生公寓：363 Adelaide St、38 Wharf St、97 Elizabeth St | 布里斯班 CBD | 明确受 **QLD《Residential Tenancies and Rooming Accommodation Act 2008》**约束，住户守则/条款随附"Notice to Remedy Breach / Notice to Leave" |
| **UniLodge** | 澳洲规模最大的学生公寓**管理方**之一 | 既管整栋公寓，也托管**大学宿舍/学院(College/Halls)**（如 La Trobe Chisholm、JCU、SCU Lismore 等） | 全澳各州 + 新西兰奥克兰 | 州租赁法 + 大学合作协议；应急管理按 **AS3745-2010** 编制 |
| **Meriton** | 悉尼最大公寓开发商之一（Triguboff 家族） | ①传统**长租公寓**（Meriton Property Management，新推 built-to-rent）②**Meriton Suites** 短/中住酒店式公寓 | 以 NSW 为主，布里斯班/黄金海岸等亦有 | 传统租赁流程走州租赁法（租户申请→租约→押金→condition report）；Suites 走住宿/酒店条款 |

---

## 2. 文档分类总览（建议 RAG 顶层分类）

这些公司给员工参考的文档基本可归为 **8 大类**，覆盖一个租户从"询价 → 入住 → 居住 → 退房 → 离店后"的全生命周期，外加应急、人力、对外合作三条横切线：

| 大类 | 英文标签(建议检索用) | 生命周期位置 | 面向 |
|---|---|---|---|
| A. 房源与预订/销售 | Sales & Booking | 询价→付订金 | 住户/代理/销售 |
| B. 合同与法律文件 | Agreements & Legal | 签约 | 住户/法务/前台 |
| C. 入住-居住-退房运营流程 | Operations SOP & Forms | 全生命周期 | 前台/礼宾/运营 |
| D. 住户守则与社区行为规范 | House Rules / Code of Conduct | 居住期 | 住户+员工执法依据 |
| E. 安全与应急管理 | Safety & Emergency | 全生命周期 | 全体员工(应急组织) |
| F. 合规、投诉与风险 | Compliance & Complaints | 横切 | 管理岗/法务 |
| G. 人力与培训 | HR & Training | 横切 | 员工 |
| H. 对外协作资料 | Partnerships & 3rd-party | 横切 | 代理/学校/家长 |

> 对 RAG 来说 A–E 是"高频被检索"的热区（员工日常要回答/执行），F/G 是"低频但高重要性"，H 常是各运营商的网站公开素材（可直接抓取增强知识库）。

---

## 3. 每一类的典型文档与大致内容

### A. 房源与预订/销售类
典型文档：
1. **房型/价格目录（Rate Card / Room Plans）**：Studio/2-5 人间、周租金、租期档（如 Student One 最短 12 周、按学期/学年）、设施清单。
2. **预订与取消条款（Booking Terms & Conditions）**——实据：Scape 官方 PDF、Student One 官方条款页。典型章节：
   - 适用范围（线上/电话/代理渠道）、"we/you" 定义、可随时修订、按物业所在州法律管辖；
   - **订金(Holding Deposit/Deposit)规则与退款**：Scape 按州区分——NSW 交 1 周租金订金、签约后抵扣首期租金；QLD 交 1 周租金 + **48 小时冷静期可全退**，之后订金转为押金一部分；VIC 14 天内须签约；SA 同 NSW；
   - **未获签证/未录取全额退款**条款（需书面证明 + 至少 2 周提前通知 + 填退款表，如 Scape Booking T&C Part 2 §7）；UniLodge 官网条款亦有 "No Visa No Pay" 栏目；
   - 预订人资格：年龄（如 Scape 要求入住时 ≥16 岁、<18 需监护人同意/担保共签；Student One 提供 U18 支持页面）、须为在读学生（入住时出示注册证明、ID、可能的背景调查；Scape 2022 版还含 COVID 疫苗要求）；
   - 付款方式（双周 direct debit / 一次性预付）、手续费；
   - 房源保留时限（如 Student One 组队订房，队友链接 **4 小时**内须完成预订）。
3. **促销/价格政策与佣金规则（Promo & Agent Commission）**：agent 预订佣金、合作校价。
4. **FAQ / 预订攻略页**：Scape、UniLodge、Student One 均公开，内容即"Q→A"对，非常适合做成 RAG 问答数据。

### B. 合同与法律文件
典型文档：
1. **住宅租赁协议（Residential Tenancy Agreement，RTA）**：标准州版租约 + 运营商附加条款（住户规则并入）；明文：不可转租、禁宠物、bond 与首期租金支付前不交房（Scape Booking T&C 原文）。
2. **标准条款与条件页（Terms & Conditions）**：网站使用条款、预订条款、隐私政策（Scape 隐私政策、Student One T&C+Privacy 均在官网页脚挂出）。
3. **Bond/押金文件**：押金收取、州押金托管系统（如 QLD RTA / NSW Rental Bonds Online）登记、退押流程。
4. **租约附件（Annexures）**：房间/公寓平面、家私清单、额外费用表、宠物/辅助犬申请、家长担保函（<18）。

### C. 入住-居住-退房运营流程（员工 SOP 的大本营）
这是"给员工参考的流程类文档"最集中的一类，常见独立文档：
1. **Leasing/Booking 处理 SOP**（详见第 4 节专题）。
2. **Check-in / Move-in 流程**：到达前通知 → ID/注册文件核验 → 签约与押金收讫 → 房间核对（含家私与设施损坏记录）→ 发钥匙/门卡（Scape 有 my.scape 欢迎页含 arrival 指引；Student One 预订确认后发"move-in 指引/带什么/到达信息/门禁/联系支持"）。
3. **Check-out / Move-out 流程**：退房预约 → 清洁检查 → 物品清点 → 押金抵扣/退还 → 钥匙回收；UniLodge 帮助中心有"物品损坏怎么办/搬出"类问答支撑流程。
4. **维护与报修流程（Maintenance）**——实据（Student One Residence Rules）：住户通过官网维修 portal 提交，**工作日处理**；住户禁止自行修电气/管道/门锁；公共区域损坏费用由同住人分摊，除非认定责任人。
5. **清洁与客房标准（Cleaning / Housekeeping SOP）**：公共区域清洁排班（可要求住户轮值）、退房深度清洁、失物招领（Scape Community Guidelines：洗衣房遗留物 7 天后可处理）、垃圾/回收规则。
6. **账务流程**：租金入账、direct debit 失败、滞纳金与欠租催缴、押金变动；Meriton 侧即典型 PM 的 rent roll/arrears 流程。
7. **房间调换/转租/续租**：入住后换房（UniLodge 帮助中心有"入住时可不可以换房"）、合同续签（Student One 官网有 Contract Renewal 入口）、违约转租的处理（RTA 通常禁转租）。
8. **投诉现场处置脚本**：噪音投诉 → 上门/电话 → 记录 → 升级（对应 House Rules 的 quiet hours 与"违反可被要求离场"）。

### D. 住户守则与社区行为规范
典型文档：**Residence Rules / House Rules / Community Guidelines / Code of Conduct / Resident Handbook**，内容高度同构，可直接对照三家原文：
- **行为与零容忍**：骚扰、霸凌（含网络霸凌）、歧视、性骚扰零容忍（Scape Community Guidelines 明确列举定义）；暴力/袭击属严重违约可"立即给 Notice to Leave"（Student One）。
- **安静时段**：如 22:00–07:00（Scape House Rules）；派对需 72 小时前书面申请活动表（Student One）。
- **吸烟/酒/毒品**：全楼禁烟、最低吸烟罚款（Student One 每条 ≥A$330）；大额酒水不得进公共区；18 岁以下禁酒；毒品零容忍可即时终止协议并报警（Scape/Student One）。
- **防火安全**：禁明火/蜡烛/香薰；烹饪限厨房；浴室排风扇使用；**住户引发火警的费用责任**（Student One 引用 QFES 收费 A$1,408.25/次；Scape House Rules 写 $1,600 起）。
- **访客/门禁**：访客须在前台登记、离场时间（如 Scape 22:00 前）、禁尾随、禁借门卡、door lockout 收费（Student One：非营业时间开门 $5 捐慈善）。
- **宠物**：除辅助犬外禁养（含鱼/昆虫）。
- **设备与公共空间**：公共区清洁、洗衣房、屋顶/露台时限、自行车停放、不得挪用家具等。
- **处罚阶梯**：警告 → **Notice to Remedy Breach（QLD Form 11）** → **Notice to Leave（Form 12）** → 终止协议不退费 → 报警/请走（各文件原文均有体现）。
- **Resident Handbook**（UniLodge 各物业曾发布，如 UniLodge South Bank 2017 版 PDF，公开渠道已下线、网络有存档副本）：把上面守则 + 物业设施 + 服务联系 + 应急联系方式汇编成册，是"住户版手册"的典型结构。

### E. 安全与应急管理（内部最重的一类文档）
实据为 UniLodge 发布的 **Emergency Response Management Plan（文档号 OPS.LIS.MP.001，按 AS3745-2010 编制）**，其目录几乎是行业模板，强烈建议直接复刻为 RAG 的分类骨架：
- **文档控制头**：文档编号、版本表（Ver/Auth/Check/App/Date/Review/Key Changes）、**每 12 个月复审**、"打印不受控(UNCONTROLLED when printed)"声明——这类元数据对 RAG 版本管理极重要。
- **站点信息**：Site Details、Building Systems、Access/Security/Communications Systems、Emergency Equipment。
- **应急组织（Emergency Control Structure）**：Chief Warden / Wardens / First Aid Officer；营业时间与非营业时间(After Hours)两套；Critical Incident Management Team 及其升级。
- **疏散管理**：疏散方案、行动不便者疏散、非营业时间疏散、集结区、禁止用电梯。
- **岗位职责**：每个角色按"Pre-Emergency / Emergency / Post-Emergency"三阶段写清做什么。
- **分场景响应规程**（该计划列了 30+ 类）：Building Fire、Bomb Threat、Active Armed Offender、Abduction/Abuse、Medical Emergency、Self-Harm、Sexual Assault、Trauma Management、Chemical Spill、Flood/Storm/Bushfire、Power Outage、Gas Leak、Structural Damage、Suspicious Mail、Rodent/Pest、Drowning、Electric Shock 等；含 Threat Assessment 风险矩阵、Incident Code Type 表。
- **应急装备与用品**：Night Manager Duty Bag、Evacuation Kit、Warden Kit 内容清单。
- **配套文档**：消防疏散图、消防演练记录、安全培训签到、WHS 手册、事件报告表(Incident Report)。

### F. 合规、投诉与风险
典型文档：
- **投诉处理流程（Complaints Process）**——实据：Scape 官网公开投诉流程页；典型结构：分级（住户→前台→物业经理→总部/独立调解）→ 时限 → 记录 → 回复与整改 → 向州仲裁庭(RTA/VCAT/NCAT)的外部途径提示。
- **隐私政策与个人信息处理**（住户信息含年龄/国籍/残障用于分房——Scape Booking T&C 原文）。
- **未成年住户合规**（U18 需学校同意 + 监护人共签/担保；UniLodge 帮助中心有 underage 申请问答；Student One 有 UQ Under-18 专项页）。
- **公平对待/反歧视政策**、**儿童安全(Child Safe)政策**（对大学合作物业尤其常见，属推断但行业标配）。
- **州法合规对照表**：各州 RTA 的差异条款（进房权、notice 期限、押金托管、纠纷处理）整理成"按州检索"的合规矩阵——非常适合 RAG 打州别 tag。
- **审计与检查表**：月/季度物业审计、房况抽查、供应商准入。

### G. 人力与培训
典型文档（企业内真实存在，公开渠道难见全文，但**岗位招聘 JD 会泄露结构**，如 Scape Night Manager 岗）：
- **员工手册(Employee Handbook)**：雇佣条款、行为准则、着装、考勤、禁骚扰。
- **岗位手册/职责说明**：Duty Manager / Night Manager / 前台(Reception/Concierge) / Leasing Consultant / Housekeeper / 维修工——每岗"日常职责 + 交接班 + 报修/投诉/门禁/锁门处理权限 + 非营业时间单兵流程"。Night Manager 的"Duty Bag"类装备与深夜场景处置往往就是其手册核心。
- **培训材料**：入职培训、系统培训(PMS/门禁/邮箱/工单)、消防疏散培训、文化敏感度与霸凌骚扰识别培训、急救培训。
- **排班与值班手册**、**对讲/沟通话术**。

### H. 对外协作资料（常是公开素材，RAG 可直接抓取）
- **给留学代理的手册/申请表**：如 IH Brisbane 为 Student One 制作的 agent 申请表/说明 PDF；佣金政策。
- **给家长的信息页**：Student One 有 "Info for Parents" 帮助页。
- **给学校的合作文件**：U18 学生支持、学院合作运营协议（UniLodge 托管大学宿舍的 SLA）。
- **网站 FAQ/帮助中心**：UniLodge 帮助中心(support.unilodge.com.au)甚至做了**中英双语**文章（申请、撤申请、换房、违规通知、报修、义务），是现成的高质量 RAG 语料。

---

## 4. 专题：以"租户前来租房的流程"为例（前台/销售侧主流程）

### 4.1 公开端可考的真实流程
- **Student One（官网 step-by-step）**：①选房型/楼栋 → ②Book now 选具体房间号与周价 → ③填个人+学业+入住日期+生活偏好(+好友) → ④进 portal 审阅 rental agreement（含房号、周价、支付信息，家长可一起看）→ ⑤**付 2 周租金作押金 + 签约 = 确认**；之后收到 move-in 指引。可全程线上、可到埠前预订；好友组队订房时队友 4 小时内完成预订否则不保留。
- **Scape（Booking T&C 推导的签约前置检查）**：预订 → 交订金（按州规则，见 §3A）→ **核验注册在读证明 / 护照签证 ID / 必要时背景调查** → 冷静期/限期内签 RTA → 付 bond+首期租金 → 交房。任一前置未满足：可取消（扣订金）或延迟起租。
- **UniLodge**：官网"how to apply"博客 + 帮助中心问答：在线申请 → 审核/联系 → 交申请相关材料 → 接受 offer → 签约；帮助中心另含"如何撤回申请""入住当天能否换房"等边界问答。
- **Meriton（传统租赁，走州法）**：租户在 2Apply（Meriton Property Management 用该平台）填申请表 → 房东/PM 审核（ID、收入/就业、租赁历史）→ 通过后签 Residential Tenancy Agreement → 交 bond（州托管系统）→ **Entry Condition Report（入住房况报告）** → 入住；租期内 routine inspection / 维修工单 / 续约 / 退租 Exit Condition Report。

### 4.2 员工侧应有但未公开的"内部 SOP"（推断结构，供文档设计）
一份完整的 Leasing/Check-in SOP 大概率长这样：
1. **询价与资格初筛**：年龄/学生身份/签证/意向租期→判定走"个人/组队/未成年/家长代订"哪条通道；
2. **报价与保留**：按房型与空房表报价；收订金(金额按州规则)；生成 Refund Form 模板备用；
3. **核验与风险检查**：注册证明、ID、参考人（租住/雇佣）→命中即触发"取消/延迟"分支（对应 Booking T&C 的取消权条款）；
4. **签约包**：RTA + House Rules 签收 + 押金收讫 + 付款方式登记（direct debit 授权）；
5. **Move-in 执行**：预约到达 → 核验原件 → 发门卡/钥匙 → 房况与家私核对表 → 首次安全/消防告知（对应"入住即须参加 fire briefing"条款）；
6. **事后归档**：系统录入、文件归档、把"何时可取消/冷静期剩余时间"记入日历提醒。
> 异常分支（每种都应在 SOP 里有对应处理条款与所需表单）：签证被拒（全额退款条件）、未录取、no-show、入住当天想换房、未成年无监护人、组队成员未按时完成预订、信用卡退款手续费、房东主动取消（虚假信息/违约）等。

---

## 5. 各公司文档实据与链接（可作 RAG 语料种子）

| 类别 | Scape | Student One | UniLodge | Meriton |
|---|---|---|---|---|
| 预订/签约条款 | [Booking T&C (2022 PDF)](https://www.scape.com.au/wp-content/uploads/2022/08/Booking-TCs-2022.pdf)（含 Refund Form 模板） | [Terms & Conditions](https://studentone.com/terms-and-conditions)；[How to book 步骤](https://studentone.com/help/how-to-book) | [Terms & Conditions（No Visa No Pay）](https://www.unilodge.com.au/terms-conditions) | 租户申请走 [2Apply(Meriton PM)](https://app.2Apply.com.au/Agency/MeritonPMLeura) |
| 退款政策 | [Refund policy](https://www.scape.com/about/refund-policy/)；[FAQs](https://www.scape.com.au/frequently-asked-questions/) | [FAQs](https://studentone.com/help/faqs) | 帮助中心多语文章：[申请/撤申请/换房/违规通知/报修/义务](https://support.unilodge.com.au/en/articles/9219522-how-can-i-apply-for-a-room-or-apartment) | — |
| 住户守则 | [House rules (合作语言学校托管PDF)](https://elc.edu.au/wp-content/uploads/2025/12/ELC_Scape_House_rules.pdf)；[Community Guidelines (PDF)](https://elc.edu.au/wp-content/uploads/2024/04/ELC_Premium_Apartment_Community_Guidelines.pdf) | [Residence Rules (PDF)](https://brownsenglish.edu.au/files/pdf/agents/bne-s1-apts-terms.pdf)（QLD RTRA 2008，含 Form 11/12） | Resident Handbook 各物业版（南岸 2017 版 PDF 原链已下线，网络存档可寻）；分物业 [FAQ](https://www.unilodge.com.au/student-accommodation-townsville/townhouses/faq) | [No Party 政策公告(PDF)](http://www.meritonapartments.com.au/media/pdfs/NOPARTY2008.pdf) |
| 应急/安全 | Sustainability Report 2024 含 [居民安全健康福祉章节](https://www.scape.com.au/wp-content/uploads/2025/07/Scape-2024-Sustainability-Report.pdf) | 守则内含消防/疏散条款 | **[Emergency Response Management Plan (PDF)](https://www.scu.edu.au/media/scu-dep/services/property-services/documents/UniLodge_-Emergency-Response-Management-Plan-v1.1.pdf)**（OPS.LIS.MP.001，AS3745-2010） | — |
| 投诉 | [Complaints Process](https://www.scape.com/about/complaints-process/) | — | — | — |
| 未成年 | — | [UQ Under 18 支持页](https://studentone.com/uq-u18s)；[给家长](https://studentone.com/help/parents) | [Can I apply if underage?](https://support.unilodge.com.au/en/articles/9219705-can-i-apply-for-a-room-apartment-if-i-am-underage) | — |
| 物业/合作素材 | [my.scape 欢迎页(含到达指引)](https://my.scape.au/quay#arrival)；[About Scape](https://www.scape.com.au/about-scape/) | [IH 为 S1 做的 agent 申请表(PDF)](https://www.ihbrisbane.com.au/wp-content/uploads/2020/02/IH-S1-agent-application-form_Feb2020.pdf) | [Apply for a room 博客](https://www.unilodge.com.au/blog/how-to-apply-for-a-room) | [MRI 合作 built-to-rent](https://eliteagent.com/meriton-and-mri-software-partner-in-built-for-rent-project/) |
| 员工岗位线索 | [Night Manager 招聘(职责披露)](https://www.seek.com.au/job/77002704) | — | — | [Meriton Property Management](https://www.meriton.com.au/propertymanagement/) |

下载到本机的原文副本（可脱机查看）：`research/scape_booking_tc.pdf`、`research/scape_house_rules.pdf`、`research/scape_community_guidelines.pdf`、`research/studentone_residence_rules.pdf`、`research/unilodge_ermp.pdf` 及其 `.txt` 文本。

---

## 6. 面向 RAG / Agentic Workflow 的落地建议

1. **按"文档类 + 用途"建顶层索引**，别按公司建文件夹：同一类文档(如 House Rules)跨公司结构高度相似，检索时可统一 schema。
2. **元数据必带**：`doc_type`、`audience`(住户/员工/代理)、`property`、`state`（NSW/QLD/VIC/SA…）、`legal_basis`(RTA 2008 等)、`effective/next_review`、`version & doc_no`（如 OPS.LIS.MP.001）、`language`(en/zh)、`source_url`、`is_internal(推断)`。**版本与州别是最容易翻车的两个维度**（如 Scape 2022 版含已过时的 COVID 条款；同一条款在 QLD 有 48h 冷静期、在 NSW 没有）。
3. **条款型文档按编号切块**（Part/Clause/§），**流程型文档按步骤+分支切块**，FAQ 按 Q-A 对切块；表单（如 Refund Form）应走**字段抽取**而非全文 RAG。
4. **处罚阶梯与时限是高频问答**：罚款金额（吸烟 $330、火警 $1,408/QFES 或 $1,600、lockout $5…）、Notice 种类(Form 11/12)、退款时限(30 天)、冷静期(48h)——建议做成结构化知识或专用问答对，减少幻觉。
5. **员工侧 Agent 的分层**：前台/Leasing Agent → 主查 A–D 类；Night Manager/Duty Manager → 主查 C/E 类(深夜场景+应急)；管理岗 → F/G。每类 Agent 配不同的文档白名单与权限。
6. **公开素材可直接入库做种子**（第 5 节链接），再按第 3 节分类骨架去补齐客户内部真实手册。

---

## 7. 局限性
- 员工手册、内部 SOP、培训材料的具体条文无法从公开渠道验证，第 3/4 节中以"推断/行业标准"标注。
- 金额、时限类条款随时间变化（罚款、火警费、疫苗要求等），引用前应核对各公司现行版本与所在州法规。
