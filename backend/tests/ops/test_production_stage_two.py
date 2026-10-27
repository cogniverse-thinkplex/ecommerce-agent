from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_production_compose_runs_isolated_periodic_backup_service():
    compose = (ROOT / "docker-compose.production.yml").read_text()
    assert "backup:" in compose
    assert "scripts/backup_daemon.py" in compose
    assert "ECOM_BACKUP_INTERVAL_SECONDS" in compose
    assert "agent-data:/app/data" in compose


def test_security_scan_is_strict_and_checks_dependencies_code_and_secrets():
    script = (ROOT / "scripts/security_scan.sh").read_text()
    assert "pip-audit" in script
    assert "bandit" in script
    assert "secret" in script.lower()
    assert "set -euo pipefail" in script


def test_production_acceptance_covers_configuration_tests_backup_and_operations():
    script = (ROOT / "scripts/production_acceptance.sh").read_text()
    for marker in (
        "validate_runtime_config", "test_backend.sh", "backup_sqlite.py",
        "restore_sqlite.py", "security_scan.sh", "check_operations.py",
    ):
        assert marker in script


def test_production_template_documents_hardening_controls():
    example = (ROOT / ".env.production.example").read_text()
    assert "ECOM_LOGIN_MAX_FAILURES=5" in example
    assert "ECOM_LOGIN_BLOCK_SECONDS=900" in example
    assert "ECOM_BACKUP_INTERVAL_SECONDS=86400" in example
    assert "ECOM_BACKUP_RETENTION=14" in example
