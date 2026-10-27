import json
import sqlite3
from pathlib import Path

import pytest

from app.operations.sqlite_backup import BackupError, create_backup, restore_backup


def _database(path: Path, value: str = "hello") -> None:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE items(value TEXT NOT NULL)")
    connection.execute("INSERT INTO items VALUES (?)", (value,))
    connection.commit()
    connection.close()


def test_backup_and_restore_round_trip_with_metadata(tmp_path: Path):
    source = tmp_path / "source.db"
    _database(source)

    result = create_backup(source, tmp_path / "backups")
    metadata = json.loads(result.metadata_path.read_text())
    restored = tmp_path / "restored.db"
    restore_backup(result.database_path, restored)

    connection = sqlite3.connect(restored)
    assert connection.execute("SELECT value FROM items").fetchone()[0] == "hello"
    connection.close()
    assert metadata["sha256"] == result.sha256
    assert metadata["size_bytes"] == result.database_path.stat().st_size


def test_restore_refuses_existing_target_without_replace(tmp_path: Path):
    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    _database(source, "new")
    _database(target, "old")

    with pytest.raises(FileExistsError):
        restore_backup(source, target)


def test_corrupt_database_is_rejected(tmp_path: Path):
    source = tmp_path / "corrupt.db"
    source.write_bytes(b"not sqlite")

    with pytest.raises(BackupError):
        create_backup(source, tmp_path / "backups")


def test_backup_retention_keeps_requested_count(tmp_path: Path):
    source = tmp_path / "source.db"
    _database(source)
    backup_dir = tmp_path / "backups"

    for index in range(3):
        create_backup(source, backup_dir, retain=2, label=f"manual-{index}")

    assert len(list(backup_dir.glob("*.db"))) == 2
    assert len(list(backup_dir.glob("*.json"))) == 2

