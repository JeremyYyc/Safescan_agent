# 住房与维修知识文档长度盘点

统计日期：2026-10-09。仅使用已有采集快照，未重新抓取或核实当前规则。

## 统计口径

- 原文均为英文，“字数”以英文单词数为主，同时提供包含空白的字符数。单词只统计英文字母组成的词，保留词内连字符和撇号，不计纯数字。
- 官方文档直接统计已提取正文 content_text，包含标题、章节标题及帮助/联系方式，不重复统计 sections。
- iFixit 统计简介与步骤文字，去掉 HTML、视频标记、裸链接；不计重复摘要、工具清单、作者及图片地址。
- 多次抓取的官方快照不重复计数，采用最后一批保存的 4 篇。

## 逐篇统计

| 文档 | 英文单词 | 字符（含空白） | 步骤 |
| --- | ---: | ---: | ---: |
| [租赁住房最低标准](texts/nsw-rental-standards.txt) | 318 | 2,036 | 不适用 |
| [紧急维修](texts/nsw-urgent-repairs.txt) | 369 | 2,353 | 不适用 |
| [如何推进租赁住房维修](texts/nsw-repair-process.txt) | 1,144 | 6,734 | 不适用 |
| [房东维修与维护责任](texts/nsw-landlord-maintenance.txt) | 966 | 6,419 | 不适用 |
| [修补石膏板墙洞](texts/104072.txt) | 280 | 1,480 | 6 |
| [维修漏水水龙头](texts/39117.txt) | 383 | 2,173 | 13 |
| [用湿式吸尘器疏通水槽](texts/182837.txt) | 469 | 2,621 | 9 |
| [更换马桶排水阀片](texts/44146.txt) | 203 | 1,150 | 5 |
| [紧固松动的马桶座圈](texts/140776.txt) | 639 | 3,656 | 7 |
| [拆卸洗衣机以检修排水泵](texts/105443.txt) | 679 | 3,924 | 16 |
| [更换门锁锁芯](texts/67174.txt) | 449 | 2,521 | 6 |

## 汇总

- 官方住房与维修流程文档：4 篇，2,797 个英文单词，17,542 个字符。
- iFixit 维修教程：7 篇，3,102 个英文单词，17,525 个字符。
- 合计：11 篇，5,899 个英文单词，35,067 个字符。

## 交付内容

- 总表.xlsx / 总表.csv：11 篇文档的标题、词数、步骤数、范围、许可、来源和正文路径。
- [index.html](index.html)：离线文档预览，展开每篇即可阅读。
- documents/：11 篇带标题、来源和步骤编号的 Markdown 正文。
- texts/：11 篇纯文本，作为词数统计输入。
- source_snapshots/：4 份官方 HTML 和 7 份 iFixit API 原始 JSON。
- documents.json / summary.json：结构化记录、原始元数据和长度统计。
- manifest.json / delivery_validation.json：文件哈希和交付检查。

中文标题是整理标签，正文未翻译。官方正文保留原有章节，教程恢复原步骤编号。Markdown 中的署名、编号不计入此前正文词数。

iFixit 共 62 个步骤，图片未下载成功；教程不是实际工单。许可及待确认使用条件沿用原记录，并未取得新的发布授权。本目录为独立于三套图片数据的第四套知识文档交付。

## 重新生成

从项目根目录依次运行 summarize_knowledge_docs.py、package_knowledge_docs.py prepare，再用内置 Node 和 artifact-tool 运行本目录 build_workbook.mjs，最后运行 package_knowledge_docs.py finalize。所有步骤离线，不重新采集。ZIP 位于本目录同级的 knowledge-documents-20261009.zip。
