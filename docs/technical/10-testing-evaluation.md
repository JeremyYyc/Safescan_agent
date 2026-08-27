# 测试与 AI 评测文档

## 1. 测试层级

- Unit：schema、规则、token、chunk、排序和权限函数。
- Integration：API + DB + object storage + mock Provider。
- Workflow：成功、重试、失败、checkpoint、人工确认和恢复。
- E2E：上传→处理→报告→聊天→PDF。
- Security：越权、上传和注入测试。
- Contract：API schema、状态转换、错误码、SSE 回放和幂等行为。
- AI Eval：检索、检测、路由、报告 groundedness。

## 2. 测试夹具

建立 `tests/fixtures`：短视频、关键帧、人工 Evidence、知识片段、模型响应和报告 golden files。外部模型测试默认 mock；少量 staging smoke 使用真实 Provider。

## 3. AI 指标

Retrieval：Recall@K、MRR、Hit Rate、citation precision；Detection：Precision/Recall/mAP；Workflow：route accuracy、schema validity、retry rate；Report：evidence coverage、groundedness、hallucination rate、建议相关性。

## 4. 评测流程

```text
数据集版本化 → 运行 baseline → 改动实验
→ 指标对比 → 人工抽样 → 通过/阻断发布
```

所有报告评测必须检查“高风险项是否有证据”“引用是否真的支持结论”“观察是否被错误升级为风险”“地区不匹配时是否拒绝合规结论”，不能只看语言流畅度。

## 5. CI 门槛

格式/类型检查、单元和集成测试通过；P0 API schema 无破坏；安全扫描无高危；AI 关键指标不低于 baseline；迁移 dry-run 无数据丢失。所有门禁由 P00 CI 自动执行，不能只依赖本地开发者自觉运行。

CI 的完整检查定义见 [CI/CD 技术文档](./13-cicd.md)。

## 6. 新能力的渐进式测试要求

新增能力必须同步增加测试并登记到 CI 能力表：API/schema 增加 contract test；数据库变更增加 migration dry-run 和回滚/幂等测试；工作流增加状态、重试、取消和恢复测试；媒体增加大小/时长/损坏文件测试；RAG 增加权限、召回、引用、无答案和注入测试；前端增加错误状态和断线恢复测试；Provider 增加 mock、超时、限流和降级测试。测试优先加入已有 job，只有隔离环境或资源需求不同才新增 job。
