from pathlib import Path

from app.auth.passwords import verify_password
from app.demo.seed_retail_customers import DEMO_CUSTOMERS, seed_demo_customers
from app.persistence.sqlite import SqliteUnitOfWork


RETAIL_DB = (
    Path(__file__).resolve().parents[3]
    / "benchmarks/data/tau2/domains/retail/db.json"
)


def test_seed_creates_five_linked_customers_idempotently(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "demo.db")
    unit.initialize()

    first = seed_demo_customers(unit, RETAIL_DB, password="DemoCustomer@123")
    second = seed_demo_customers(unit, RETAIL_DB, password="DemoCustomer@123")

    assert len(first) == len(second) == 5
    for expected in DEMO_CUSTOMERS:
        user = unit.users.get_by_email(expected.email)
        assert user is not None
        assert user.user_id == expected.platform_user_id
        assert user.display_name == expected.display_name
        assert user.retail_user_id == expected.retail_user_id
        assert user.role == "customer"
        assert verify_password("DemoCustomer@123", user.password_hash)


def test_seed_rejects_retail_customer_without_orders(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "demo.db")
    unit.initialize()
    retail_db = tmp_path / "retail.json"
    retail_db.write_text(
        '{"users": {"ivan_santos_6635": {}}, "orders": {}, "products": {}}',
        encoding="utf-8",
    )

    try:
        seed_demo_customers(unit, retail_db, password="DemoCustomer@123")
    except ValueError as exc:
        assert "订单" in str(exc)
    else:
        raise AssertionError("缺少订单的 Retail 用户不应被写入平台数据库")
