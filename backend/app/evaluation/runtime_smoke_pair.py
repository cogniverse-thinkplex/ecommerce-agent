from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from app.evaluation.runtime_smoke import build_smoke_markdown_report, run_runtime_smoke
from app.evaluation.smoke_compare import SmokeComparison, compare_smoke_runs


class RuntimeSmokePairResult(BaseModel):
    rule_run: str
    llm_run: str
    rule_artifact_path: Path
    llm_artifact_path: Path
    report_path: Path
    comparison: SmokeComparison


def run_runtime_smoke_pair(
    *,
    simulations_dir: Path,
    report_dir: Path = Path("docs/smoke"),
    max_steps: int = 6,
    timestamp: str | None = None,
) -> RuntimeSmokePairResult:
    resolved_timestamp = timestamp or _timestamp()
    rule_run = f"smoke-rule-{resolved_timestamp}"
    llm_run = f"smoke-llm-{resolved_timestamp}"
    report_path = report_dir / f"smoke-pair-{resolved_timestamp}.md"

    rule_artifact_path = run_runtime_smoke(
        simulations_dir=simulations_dir,
        planner_type="rule",
        max_steps=max_steps,
        run_name=rule_run,
    )
    llm_artifact_path = run_runtime_smoke(
        simulations_dir=simulations_dir,
        planner_type="llm",
        max_steps=max_steps,
        run_name=llm_run,
    )
    comparison = compare_smoke_runs(
        simulations_dir,
        baseline_run=rule_run,
        candidate_run=llm_run,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        build_smoke_markdown_report(
            json.loads(Path(llm_artifact_path).read_text()),
            comparison=comparison,
        )
    )
    return RuntimeSmokePairResult(
        rule_run=rule_run,
        llm_run=llm_run,
        rule_artifact_path=Path(rule_artifact_path),
        llm_artifact_path=Path(llm_artifact_path),
        report_path=report_path,
        comparison=comparison,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run rule and LLM runtime smoke runs.")
    parser.add_argument("--simulations-dir", required=True)
    parser.add_argument("--report-dir", type=Path, default=Path("docs/smoke"))
    parser.add_argument("--max-steps", type=int, default=6)
    parser.add_argument("--timestamp", help="Optional stable timestamp for reproducible run names.")
    args = parser.parse_args(argv)

    result = run_runtime_smoke_pair(
        simulations_dir=Path(args.simulations_dir),
        report_dir=args.report_dir,
        max_steps=args.max_steps,
        timestamp=args.timestamp,
    )
    print(f"rule_smoke_artifact={result.rule_artifact_path}")
    print(f"llm_smoke_artifact={result.llm_artifact_path}")
    print(f"smoke_pair_report={result.report_path}")
    print(f"smoke_pair_regressions={result.comparison.regression_count}")
    print(f"smoke_pair_improvements={result.comparison.improvement_count}")
    return 0


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
