# Critic / Reflection: E8 Outcome Regression

## 目标

把“到达正确写工具”升级为“工具和参数正确、确认执行成功、数据库状态确实变化”，并建立覆盖主要 Retail 写场景的稳定代表集。

## 产物

- Artifact: `benchmarks/data/simulations/regression-rule-e8-outcome/runtime_subset.json`
- Report: `docs/smoke/regression-rule-e8-outcome.md`
- Runner: `scripts/run_runtime_regression.sh`
- Manifest: exchange `0`、return `2`、cancel `38`、address update `17`、payment update `40`

## 验证规则

1. 从 task expected actions 中寻找最后一个目标写操作。
2. 待确认工具名及完整参数必须与 expected action 一致。
3. 只有匹配时才允许测试 runner 自动确认。
4. 执行事件不得包含 tool error。
5. 确认前后数据库哈希必须变化，才判定 `confirmed_state_verified`。
6. 自动确认前会重新核对当前 pending action 的工具名、完整参数和重新计算的 fingerprint，防止过期检查确认其他操作。

## Rule Baseline

- Tasks: `5`
- Business success: `2/5` (`40%`)
- Exact match: `1/5` (`20%`)
- Average steps: `3.00`
- Total cost: `0`
- Confirmation gate success: `2/5`
- Confirmed outcome success: `2/5`
- Confirmed state verified: exchange、return
- Target not reached: cancel、address_update、payment_update

## 结论

E8 的价值不是把分数做高，而是让分数可解释。换货和退货现在有参数及落库证据；另外三类失败明确停在 planner 能力缺失，而不是评测器误判。下一轮应直接补齐通用业务 flow，并以同一代表集验证从 `2/5` 到 `5/5`。

普通 smoke 到达 confirmation gate 时只记录门禁成功，不再描述为已落库完成。真实 LLM 调用若无法取得 provider usage，成本字段为 `null`，Dashboard 和报告显示 `N/A`。
