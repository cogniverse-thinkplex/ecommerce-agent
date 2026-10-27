# E12 Routing Recovery Implementation Plan

**Goal:** Improve the three E11 failure cases without task-id branches.

**Approach:** Generalize return-target extraction so information-only items never enter write arguments, strengthen mixed-intent planner guidance, and give long workflows enough steps to reach their expected write. Validate locally first, then rerun only tasks 2, 48, and 71 with the configured LLM.

**Acceptance:** Existing tests stay green; focused rule behavior selects the air purifier rather than the informational vacuum; the three-task LLM recovery run reaches at least two confirmed outcomes within the existing CNY 0.02/task budget.

