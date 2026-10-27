# Critic / Reflection: E7 Business Success

## 目标

将 tau2 generated trajectory 的严格动作序列匹配与实际业务目标完成情况分开，避免正确完成退货流程的 task 因额外读操作被误判为业务失败。

## 实现

- `SessionTaskCheck` 新增 `business_success` 和 `business_success_basis`。
- Runtime subset 新增业务成功汇总、业务失败 task 列表和按 task 的 step budget。
- task `2` 的 smoke step budget 从默认 `6` 提升到 `10`。
- failure summary 记录 recovery kinds；已恢复 rejection 不再优先归类为失败。
- Dashboard、评测汇总、对比和 smoke Markdown 报告同时展示严格匹配与业务成功。

## 确定性验证证据

- Artifact: `benchmarks/data/simulations/smoke-rule-e7-business-success/runtime_subset.json`
- Report: `docs/smoke/smoke-rule-e7-business-success.md`
- Total tasks: `3`
- Exact match: `2/3`
- Business success: `3/3`
- Business failed task ids: `[]`
- task `2`: `step_budget=10`、`business_success_basis=target_write_pending`、`failure_summary.category=business_success`

## 结论

task `2` 的动作轨迹仍与 generated trajectory 不完全一致，因此严格匹配保持失败；但实际流程已正确到达 `return_delivered_order_items` confirmation gate，因此业务结果成功。两个指标现在可分别用于行为审计和产品质量判断。

## 下一轮建议

扩展代表性任务簇，并把 outcome evaluator 提升为可配置规则：不仅验证目标写工具是否到达 confirmation gate，还应验证确认后的状态变更及关键参数是否正确。
