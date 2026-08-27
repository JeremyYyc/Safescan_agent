# LangGraph 工作流文档

## 1. State

```python
class SafeScanState(TypedDict):
    inspection_id: str
    user_id: str
    evidence: list[Evidence]
    retrieved_context: list[RetrievedChunk]
    hazards: list[Hazard]
    compliance: list[ComplianceFinding]
    scores: list[RiskScore]
    recommendations: list[Recommendation]
    report: Report | None
    approval_required: list[str]
    errors: list[WorkflowError]
    trace: list[TraceEvent]
```

## 2. Nodes

`load_inspection` → `build_evidence` → `plan_context` → 并行 `hazard_analysis`/`comfort_analysis` → `retrieve_safety` → 并行 `compliance`/`scoring` → `recommendation` → `write_report` → `validate_report`。MVP 不执行法规检索和合规节点；后续启用时必须先校验 jurisdiction。

验证失败进入 `repair_report`，超过上限进入 `failed`；MVP 的高风险低置信度进入 `approval_required` 标记并完成报告，P1 才进入 `interrupt/approval`，确认后从 checkpoint 继续。

## 3. 重试规则

网络/限流/临时服务错误可重试；schema 错误最多 repair + retry 两次；权限、媒体损坏、知识不存在等确定性错误不重试。每次重试写入 workflow event。

## 4. 幂等与恢复

节点以 `(workflow_run_id, node_name, input_hash)` 作为幂等键。checkpoint 与输出持久化后才推进状态。重复消费不会重复生成报告或重复写 citation。每个 run 只能有一个 published report；重试 run 只能发布新版本。

## 5. 终态与状态转换

```text
created → queued → running → completed
                    ├→ waiting_confirmation → running
                    ├→ failed → queued (retry)
                    └→ cancelled
```

`completed`、`failed`、`cancelled` 为终态；只有服务层允许的状态转换才能执行，客户端不能直接写状态。

## 6. AutoGen 迁移

先实现 LangGraph adapter，使新图调用现有 Agent；再把 Agent 内部输出改为 schema；最后替换具体实现。灰度期间同一输入可采样双跑，比较关键字段和指标。
