from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.operations.operational_checks import run_operational_checks


def test_operational_checks_report_healthy_state(tmp_path: Path):
    backup = tmp_path / "latest.db"
    backup.write_bytes(b"backup")
    now = datetime.now(timezone.utc)

    result = run_operational_checks(
        ready_probe=lambda: {"status": "ready"},
        backup_dir=tmp_path,
        max_backup_age=timedelta(hours=26),
        now=now,
        disk_usage=lambda _path: (100, 50, 50),
    )

    assert result.ok is True
    assert all(check.status == "ok" for check in result.checks)


def test_operational_checks_fail_for_unready_stale_backup_and_low_disk(tmp_path: Path):
    backup = tmp_path / "old.db"
    backup.write_bytes(b"backup")
    old_timestamp = (datetime.now(timezone.utc) - timedelta(days=2)).timestamp()
    import os
    os.utime(backup, (old_timestamp, old_timestamp))

    result = run_operational_checks(
        ready_probe=lambda: {"status": "not_ready"},
        backup_dir=tmp_path,
        max_backup_age=timedelta(hours=26),
        now=datetime.now(timezone.utc),
        min_disk_free_ratio=0.2,
        disk_usage=lambda _path: (100, 90, 10),
    )

    assert result.ok is False
    assert {check.code for check in result.checks if check.status == "error"} == {
        "service_not_ready", "backup_stale", "disk_space_low"
    }


def test_operational_checks_fail_when_no_backup_exists(tmp_path: Path):
    result = run_operational_checks(
        ready_probe=lambda: {"status": "ready"},
        backup_dir=tmp_path,
        now=datetime.now(timezone.utc),
        disk_usage=lambda _path: (100, 50, 50),
    )
    assert result.ok is False
    assert any(check.code == "backup_missing" for check in result.checks)

