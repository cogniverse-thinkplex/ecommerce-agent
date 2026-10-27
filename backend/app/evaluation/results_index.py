from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel


class EvaluationRunIndexItem(BaseModel):
    run_name: str
    has_results: bool
    run_type: str
    run_group: str = "adhoc"
    is_smoke: bool = False
    summary_url: str | None
    updated_at: datetime | None


class EvaluationRunIndex(BaseModel):
    runs: list[EvaluationRunIndexItem]


def list_evaluation_runs(simulations_dir: Path) -> list[EvaluationRunIndexItem]:
    if not simulations_dir.exists():
        return []

    runs: list[EvaluationRunIndexItem] = []
    for run_dir in sorted(path for path in simulations_dir.iterdir() if path.is_dir()):
        results_file = run_dir / "results.json"
        runtime_subset_file = run_dir / "runtime_subset.json"
        has_results = results_file.exists() or runtime_subset_file.exists()
        run_type = _run_type(results_file, runtime_subset_file)
        runs.append(
            EvaluationRunIndexItem(
                run_name=run_dir.name,
                has_results=has_results,
                run_type=run_type,
                run_group=_run_group(run_dir.name),
                is_smoke=_is_smoke_run(run_dir.name),
                summary_url=(
                    f"/evaluations/{run_dir.name}/summary" if has_results else None
                ),
                updated_at=_updated_at(_updated_path(run_dir, results_file, runtime_subset_file)),
            )
        )
    return runs


def _updated_at(path: Path) -> datetime | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _run_type(results_file: Path, runtime_subset_file: Path) -> str:
    if results_file.exists():
        return "tau2"
    if runtime_subset_file.exists():
        return "runtime_subset"
    return "unknown"


def _run_group(run_name: str) -> str:
    if _is_smoke_run(run_name):
        return "smoke"
    if run_name.startswith("regression-"):
        return "regression"
    return "adhoc"


def _is_smoke_run(run_name: str) -> bool:
    return run_name.startswith("smoke-")


def _updated_path(
    run_dir: Path,
    results_file: Path,
    runtime_subset_file: Path,
) -> Path:
    if results_file.exists():
        return results_file
    if runtime_subset_file.exists():
        return runtime_subset_file
    return run_dir
