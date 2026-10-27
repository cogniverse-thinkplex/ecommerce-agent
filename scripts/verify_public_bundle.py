from __future__ import annotations

import re
import sys
from pathlib import Path


PROHIBITED_PARTS = {
    ".env",
    ".env.production",
    ".idea",
    ".superpowers",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "backups",
    "models",
}
PROHIBITED_SUFFIXES = {".db", ".db-shm", ".db-wal", ".pem", ".key"}
TEXT_SUFFIXES = {
    ".css", ".env", ".example", ".html", ".ini", ".js", ".json", ".md",
    ".mjs", ".py", ".sh", ".sql", ".toml", ".txt", ".yaml", ".yml",
}
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]
PLACEHOLDER_MARKERS = {
    "should-never-appear", "your-key", "your_key", "example", "<local secret>",
}


def _local_secret_values(source_root: Path) -> list[str]:
    env_path = source_root / ".env"
    if not env_path.exists():
        return []
    values: list[str] = []
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if not any(marker in key.upper() for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            continue
        value = value.strip().strip("'").strip('"')
        if len(value) >= 12:
            values.append(value)
    return values


def verify(bundle: Path, source_root: Path | None = None) -> list[str]:
    issues: list[str] = []
    local_secrets = _local_secret_values(source_root) if source_root else []
    for path in bundle.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(bundle)
        if any(part in PROHIBITED_PARTS for part in relative.parts):
            issues.append(f"prohibited path: {relative}")
        if any(path.name.endswith(suffix) for suffix in PROHIBITED_SUFFIXES):
            issues.append(f"prohibited sensitive file: {relative}")
        size = path.stat().st_size
        if size > 100 * 1024 * 1024:
            issues.append(f"file exceeds GitHub 100 MiB limit: {relative}")
        if path.suffix.lower() not in TEXT_SUFFIXES or size > 5 * 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lowered = text.lower()
        for secret in local_secrets:
            if secret in text:
                issues.append(f"local .env value found in: {relative}")
        for pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                context = lowered[max(0, match.start() - 30):match.end() + 30]
                if not any(marker in context for marker in PLACEHOLDER_MARKERS):
                    issues.append(f"potential secret pattern in: {relative}")
    return sorted(set(issues))


def main() -> int:
    if len(sys.argv) not in {2, 3}:
        print("usage: verify_public_bundle.py BUNDLE_DIR [SOURCE_ROOT]", file=sys.stderr)
        return 2
    bundle = Path(sys.argv[1]).resolve()
    source = Path(sys.argv[2]).resolve() if len(sys.argv) == 3 else None
    if not bundle.is_dir():
        print(f"bundle does not exist: {bundle}", file=sys.stderr)
        return 2
    issues = verify(bundle, source)
    if issues:
        print("public_bundle_check=failed")
        for issue in issues:
            print(f"- {issue}")
        return 1
    files = [path for path in bundle.rglob("*") if path.is_file()]
    print("public_bundle_check=clean")
    print(f"files={len(files)}")
    print(f"bytes={sum(path.stat().st_size for path in files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

