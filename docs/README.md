# Safescan 员工侧知识库（RAG Corpus）— 说明与索引

> 语料库**现存放于 `dify/Internal_kb/01…08`**（Dify 项目目录下）。本文档为入口说明，正文目录以 `dify/Internal_kb` 为准。
> **免责声明**：全部文档为虚构企业 **Safescan Pty Ltd**（长租 + 学生公寓双业务，澳洲多州运营）的内部模板，用于系统演示与检索验证；不构成法律意见或对任何真实公司的描述。凡涉法规内容，以各州官方现行版本为准（官方来源清单见 `kb_build/02_法规基线与官方来源.md`）。

## 导入建议（Dify）
- 在 Dify 知识库中导入 **`dify/Internal_kb/` 下的 8 个分类子目录**（`01_…` ~ `08_…`），不要导入本说明与项目其它设计文档。
- 每篇文档头部含 YAML front matter（`doc_id / title / category / doc_type / audience / business_line / states / effective / owner / review_cycle / legal_basis / related / version`），可作为知识库元数据字段；其中 `doc_id`、`states`、`business_line`、`audience` 可用于检索过滤，`related` 用于确定性跳转与图谱（见 `kb_build/build_doc_graph.py`）。
- 正文使用多级 Markdown 标题与编号条款，适合按标题切分（chunk by heading）；SOP 类按"步骤 + 异常分支"分段。

## 目录索引（93 篇，2025-09 版）

| 分类目录 | 前缀 | 文档数 | 体量 |
|---|---|---|---|
| 01_员工政策与组织管理 | SC-EMP-001~009 | 9 | ≈248 KB |
| 02_岗位角色与操作SOP | SC-SOP-001~014 | 14 | ≈436 KB |
| 03_租赁产品与客户政策 | SC-PRD-001~010 | 10 | ≈204 KB |
| 04_合同、Bond与争议处置 | SC-LGL-001~011 | 11 | ≈228 KB |
| 05_居住规则、投诉与住户保护 | SC-HSR-001~012 | 12 | ≈312 KB |
| 06_安全、应急与现场风险 | SC-SAF-001~014 | 14 | ≈400 KB |
| 07_培训、供应商与外部协作 | SC-TRN-001~011 | 11 | ≈272 KB |
| 08_法规与属地合规 | SC-REG-001~012 | 12 | ≈276 KB |
| 合计 | | **93** | ≈2.4 MB |

校验方式：`python3 kb_build/qa_corpus.py`（编号齐全、front matter 13 键、≥8KB、文档控制与免责声明，0 问题）。
写作规范、公司设定、法规基线、分类目录与图谱工具见项目根 `kb_build/`（不属于知识库导入范围）。
