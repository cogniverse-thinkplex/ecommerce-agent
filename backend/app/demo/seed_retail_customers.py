from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path

from app.auth.passwords import hash_password
from app.persistence.models import UserRecord
from app.persistence.sqlite import SqliteUnitOfWork


@dataclass(frozen=True)
class DemoCustomer:
    platform_user_id: str
    retail_user_id: str
    email: str
    display_name: str


DEMO_CUSTOMERS = (
    DemoCustomer(
        "demo-retail-ivan-santos",
        "ivan_santos_6635",
        "ivan.santos3158@example.com",
        "Ivan Santos",
    ),
    DemoCustomer(
        "demo-retail-anya-garcia",
        "anya_garcia_3271",
        "anya.garcia2061@example.com",
        "Anya Garcia",
    ),
    DemoCustomer(
        "demo-retail-aarav-anderson",
        "aarav_anderson_8794",
        "aarav.anderson9752@example.com",
        "Aarav Anderson",
    ),
    DemoCustomer(
        "demo-retail-isabella-sanchez",
        "isabella_sanchez_2068",
        "isabella.sanchez6218@example.com",
        "Isabella Sanchez",
    ),
    DemoCustomer(
        "demo-retail-olivia-jackson",
        "olivia_jackson_1219",
        "olivia.jackson2465@example.com",
        "Olivia Jackson",
    ),
)


def seed_demo_customers(
    unit: SqliteUnitOfWork,
    retail_db_path: Path,
    *,
    password: str,
) -> list[UserRecord]:
    retail_data = json.loads(retail_db_path.read_text(encoding="utf-8"))
    retail_users = retail_data.get("users", {})
    retail_orders = retail_data.get("orders", {})

    for customer in DEMO_CUSTOMERS:
        if customer.retail_user_id not in retail_users:
            raise ValueError(f"Retail 用户不存在：{customer.retail_user_id}")
        if not any(
            order.get("user_id") == customer.retail_user_id
            for order in retail_orders.values()
        ):
            raise ValueError(f"Retail 用户没有订单：{customer.retail_user_id}")

    seeded: list[UserRecord] = []
    for customer in DEMO_CUSTOMERS:
        existing = unit.users.get_by_email(customer.email)
        values = {
            "email": customer.email,
            "display_name": customer.display_name,
            "password_hash": hash_password(password),
            "role": "customer",
            "status": "active",
            "must_change_password": False,
            "retail_user_id": customer.retail_user_id,
        }
        if existing is None:
            record = UserRecord(user_id=customer.platform_user_id, **values)
            with unit.transaction():
                unit.users.create(record)
        else:
            record = existing.model_copy(update=values)
            with unit.transaction():
                unit.users.update(record)
        seeded.append(record)
    return seeded


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    sqlite_path = Path(
        os.getenv("ECOM_AGENT_SQLITE_PATH", str(root / "data/ecommerce_agent.db"))
    )
    retail_db_path = Path(
        os.getenv(
            "ECOM_RETAIL_DB_PATH",
            str(root / "benchmarks/data/tau2/domains/retail/db.json"),
        )
    )
    password = os.getenv("ECOM_DEMO_CUSTOMER_PASSWORD", "DemoCustomer@123")
    unit = SqliteUnitOfWork(sqlite_path)
    unit.initialize()
    users = seed_demo_customers(unit, retail_db_path, password=password)
    print(f"已写入 {len(users)} 个演示客户：")
    for user in users:
        print(f"- {user.display_name}: {user.email} -> {user.retail_user_id}")


if __name__ == "__main__":
    main()
