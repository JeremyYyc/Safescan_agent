# 数据采集试点计划

- 日期：2026-09-28
- 分支：`codex/data-collection-pilot`，从当前本地 `main` 创建。
- 状态：5 页试采已执行，4 篇成功、1 个来源 403；清洗和去重复验完成，尚未入库。见 [采集结果](DATA-COLLECTION-PILOT-RESULTS.zh-CN.md)。
- 首轮默认地区：澳大利亚 NSW，与现有部分房源种子一致；这是试点范围，不代表产品仅支持 NSW。
- 目标：获得可追溯、可人工检查的小批量安全与维修资料，验证采集和清洗质量，再决定知识库接入。

## 1. 数据范围

| 数据 | 首轮处理 | 真实性要求 |
|---|---|---|
| 员工、客户、权限和管理范围 | 后续统一生成种子数据 | 标记 synthetic，使用虚构身份 |
| 房源属性、申请、租约、签署事件、账单 | 后续按关联关系生成 | 演示数据，不作为市场分析或真实交易依据 |
| 维修工单、分派、状态、评论时间线 | 后续生成 20 条关联演示工单 | 模拟记录不能标成真实维修历史 |
| 家庭消防、住房要求、报修流程 | 首轮采集 5 页，再扩到最多 20 篇 | 官方原文、地区、版本和来源可追溯 |
| 设备维护手册 | 第二批选择 2 个明确型号，各收 1 份官方手册 | 保留品牌、型号、语言、版本；型号未选定前不广泛采集 |
| 真实维修案例 | 后续目标 5 个有处理结果的授权案例 | 现象、检查、处理、验收；未知项保持为空 |
| 视频与现场照片 | 后续目标 5 段授权巡检视频、3 组同案例维修前后照片 | 保留授权和拍摄关系，不把生成素材当真实证据 |
| 评测答案 | 根据样本人工标注 10 个可核验问题 | 模型可辅助整理，不能自行成为评测真值 |

首轮采集的是维修知识，不是实际维修记录。官方“如何报修”文章不能冒充一次已经发生且成功完成的维修。

## 2. 首批来源清单

以下页面已于规划时通过网页工具发现或访问；抓取许可、robots 和正文提取质量仍需在实施时检查。

| ID | 页面 | 用途 |
|---|---|---|
| nsw-fire-checklist | [Home fire safety checklist](https://www.fire.nsw.gov.au/fire-safety/home-fire-safety/topics/home-fire-safety-checklist) | 家庭消防检查知识 |
| nsw-rental-standards | [Minimum standards for rental properties](https://www.nsw.gov.au/housing-and-construction/rules/minimum-standards-for-rental-properties) | 住房基本要求 |
| nsw-urgent-repairs | [Urgent repairs in residential rental properties](https://www.nsw.gov.au/housing-and-construction/rules/urgent-repairs-residential-rental-properties) | 紧急维修分类 |
| nsw-repair-process | [Getting repairs done on a rental property](https://www.nsw.gov.au/housing-and-construction/renting-a-place-to-live/getting-repairs-done) | 报修与处理流程 |
| nsw-landlord-maintenance | [Landlord responsibilities for repair and maintenance](https://www.nsw.gov.au/housing-and-construction/rules/landlord-obligations-and-responsibilities-for-rental-properties) | 维修职责知识 |

扩充到 20 篇时，只加入人工选中的同地区官方相关页面，不递归爬取整个网站。安全指南与法定要求分别标记；官方说明页不能直接标为法律原文。首批保留英文原文，中文摘要属于派生内容，需链接回原文。

## 3. 输出内容与字段

知识文档输出 JSONL，每篇至少包含：

- `document_id`、`source_id`、`source_url`、`final_url`、`title`、`publisher`。
- `document_type`：`safety_guide`、`rental_guidance`、`repair_guidance` 或 `device_manual`。
- `jurisdiction`、`language`、`topics`。
- `published_at`、`source_updated_at`、`retrieved_at`；网页没有的日期为 null，不猜测生效日期。
- `content_text`、`sections`（保留标题和列表）、`raw_sha256`、`text_sha256`。
- `http_status`、`content_type`、`etag`、`last_modified`（如提供）。
- `rights_url`、`rights_status`、`review_status`、`extraction_warnings`。
- `provenance_type=official_publication`；翻译和摘要另存派生记录并关联原文。

真实维修案例独立建 manifest，记录 `case_id`、来源、授权、房间/设备、故障现象、检查结果、原因、处理、验收、未知项、证据附件和核验状态。不得与 synthetic 工单混淆。

视觉素材 manifest 记录 `asset_id`、`case_id` 或演示房源关联、来源/授权、媒体类型、哈希、时长/尺寸、拍摄阶段、证据时间点和标注。不得为了关联业务而声称素材来自不相关的真实房源。

## 4. 实施步骤

### A. 5 页试采

1. 新建独立采集目录 `scripts/data_collection/`，先读取项目依赖，复用可用 HTTP 客户端和 HTML 解析器。
2. 建立固定来源 manifest，支持 dry-run 列出 URL 和预算。
3. 检查站点访问规则与内容使用条件；明确限制的来源跳过并记录原因，授权不明的内容不发布原文。
4. 每域并发 1，请求间隔至少 2 秒，单请求超时 20 秒、最多重试 2 次；遵循 Retry-After，403/持续 429 停止该来源。
5. 单页上限 5 MiB，整轮网络尝试最多 30 次、响应体预算 50 MiB；限制重定向次数，并校验目标仍在允许域名。
6. 提取主正文、标题、段落和列表，去导航页脚，保留来源；记录失败页，不绕过登录或验证码。
7. 保存抓取结果、清洗结果和运行摘要。前 5 篇逐篇人工对照原网页审核。

建议产物位置为 `data/collection-pilot/<run_id>/`，在实施时加入 Git 忽略。来源配置、schema、代码、小型人工构造测试夹具和采集摘要可提交；抓取正文与媒体不直接提交 Git。原始资料先作为离线研究产物，不写业务数据库或运行中 MinIO。

### B. 扩充与验证

1. 5 页审核合格后，扩展 allowlist 至最多 20 篇，覆盖消防、住房要求和报修流程。
2. 用内容哈希去重，重复运行不新增重复文档；原文变化时保留新版本。
3. 测试标题/列表保留、导航剔除、日期缺失、重复内容、超时、限流及 HTML/PDF 类型识别。首轮遇 PDF 记录待处理，不把二进制当 HTML。
4. 人工编写 10 个问题及可支持答案的原文段落，加入无答案和不适用地区的问题。
5. 输出覆盖率、失败列表、待核验字段、重复数和使用限制，不用抓取数量代替质量结论。

### C. 维修案例与媒体

1. 通过授权导出或公开许可取得真实维修案例；没有真实案例时保持空缺，不用生成内容填充真实性指标。
2. 准备少量授权视频和维修前后照片，人工核验同案例关系；避免为拍摄而制造真实危险。
3. 建立独立人工标注，区分可见事实、风险推测和需要现场检测的项目。
4. 维修附件目前属于待实现能力，首批仅建立离线素材和 manifest，后续再增加附件上传、授权与关联。

### D. 接入业务与知识库

1. 统一生成两端共享的模拟房源、客户、租约、账单和工单，通过合法状态流转保持关系一致。
2. 再实现 knowledge-service 的解析、版本、权限、检索；原文进入私有 MinIO，元数据和切片归 knowledge schema。
3. 将带来源检索接入报告或维修辅助流程，并用人工问题集评估。
4. 本阶段另行实施；本计划不把资料下载成功视为业务已接入，也不启动训练或付费模型评测。

## 5. 首轮验收

- 5 个目标页面均有成功或明确失败记录；失败不使用生成正文补齐。
- 通过审核的每篇文档均具备来源、地区、采集时间、正文、哈希和使用状态。
- 人工逐页确认标题、关键列表和正文完整，无明显导航污染；过短或可疑结果需复核。
- 缺失日期为 null；官方说明、手册、真实案例和模拟数据可区分。
- 重跑不产生重复文档；失败重试、预算和域名限制生效。
- 提交采集摘要和样本字段展示，未审核记录不能成为已发布知识。
- 未改变现有服务、业务数据或用户已有的 docker-compose.yml 修改。

## 6. 下一次执行的具体任务

实现固定来源采集器和 5 页试采，输出清洗后的 JSONL、运行摘要及人工核验结果。若来源访问失败，保留错误并使用其他已审核的官方来源；不自动扩大到论坛、房源平台或短视频平台。
