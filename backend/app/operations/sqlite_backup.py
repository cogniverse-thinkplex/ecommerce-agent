from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4


class BackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackupResult:
    database_path: Path
    metadata_path: Path
    sha256: str


@dataclass(frozen=True)
class RestoreResult:
    target_path: Path
    safety_backup_path: Path | None


def create_backup(
    source: Path | str,
    destination_dir: Path | str,
    retain: int = 14,
    label: str | None = None,
) -> BackupResult:
    source_path = Path(source).resolve()
    if not source_path.is_file():
        raise BackupError(f"SQLite source does not exist: {source_path}")
    destination = Path(destination_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe_label = _safe_label(label or timestamp)
    final_path = destination / f"{safe_label}.db"
    temp_path = destination / f".{safe_label}.{uuid4().hex}.tmp"
    try:
        source_connection = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
        target_connection = sqlite3.connect(temp_path)
        source_connection.backup(target_connection)
        target_connection.close()
        source_connection.close()
        _assert_integrity(temp_path)
        temp_path.replace(final_path)
    except (sqlite3.Error, OSError) as exc:
        temp_path.unlink(missing_ok=True)
        raise BackupError(f"SQLite backup failed: {type(exc).__name__}") from exc

    digest = _sha256(final_path)
    metadata_path = final_path.with_suffix(".json")
    metadata_path.write_text(
        json.dumps(
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source": str(source_path),
                "database": final_path.name,
                "size_bytes": final_path.stat().st_size,
                "sha256": digest,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _apply_retention(destination, retain)
    return BackupResult(final_path, metadata_path, digest)


def restore_backup(
    source: Path | str, target: Path | str, replace: bool = False
) -> RestoreResult:
    source_path = Path(source).resolve()
    target_path = Path(target).resolve()
    _assert_integrity(source_path)
    if target_path.exists() and not replace:
        raise FileExistsError(f"Restore target already exists: {target_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    safety: Path | None = None
    if target_path.exists():
        safety = target_path.with_name(f"{target_path.name}.pre-restore-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
        target_path.replace(safety)
    temp_path = target_path.with_name(f".{target_path.name}.{uuid4().hex}.tmp")
    try:
        source_connection = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
        target_connection = sqlite3.connect(temp_path)
        source_connection.backup(target_connection)
        target_connection.close()
        source_connection.close()
        _assert_integrity(temp_path)
        temp_path.replace(target_path)
    except (sqlite3.Error, OSError) as exc:
        temp_path.unlink(missing_ok=True)
        if safety and not target_path.exists():
            safety.replace(target_path)
        raise BackupError(f"SQLite restore failed: {type(exc).__name__}") from exc
    return RestoreResult(target_path, safety)


def _assert_integrity(path: Path) -> None:
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        result = connection.execute("PRAGMA integrity_check").fetchone()
        connection.close()
    except sqlite3.Error as exc:
        raise BackupError(f"SQLite integrity check failed: {type(exc).__name__}") from exc
    if not result or result[0] != "ok":
        raise BackupError("SQLite integrity check failed")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_label(label: str) -> str:
    normalized = "".join(character for character in label if character.isalnum() or character in "-_")
    if not normalized:
        raise ValueError("Backup label must contain a letter or number")
    return normalized[:100]


def _apply_retention(directory: Path, retain: int) -> None:
    if retain < 1:
        raise ValueError("retain must be at least 1")
    backups = sorted(directory.glob("*.db"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
    for database in backups[retain:]:
        database.unlink(missing_ok=True)
        database.with_suffix(".json").unlink(missing_ok=True)

