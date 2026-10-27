from pathlib import Path

from app.persistence.models import CustomerAddressRecord, UserRecord
from app.persistence.sqlite import SqliteUnitOfWork


def test_customer_addresses_are_owner_scoped_and_logically_archived(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "addresses.db")
    unit.initialize()
    with unit.transaction():
        unit.users.create(UserRecord(user_id="u1", email="u1@example.com", display_name="One", password_hash="x", role="customer"))
        unit.users.create(UserRecord(user_id="u2", email="u2@example.com", display_name="Two", password_hash="x", role="customer"))
    first = CustomerAddressRecord(
        address_id="a1", owner_user_id="u1", recipient_name="Alice", phone="13800000000",
        address1="1 Main St", city="Austin", state="TX", country="USA", zip="78701", is_default=True,
    )
    second = first.model_copy(update={"address_id": "a2", "owner_user_id": "u2", "is_default": False})
    with unit.transaction():
        unit.customer_addresses.create(first)
        unit.customer_addresses.create(second)

    assert [item.address_id for item in unit.customer_addresses.list_for_owner("u1")] == ["a1"]
    assert unit.customer_addresses.get_for_owner("a1", "u2") is None
    with unit.transaction():
        assert unit.customer_addresses.archive_for_owner("a1", "u1") is True
    assert unit.customer_addresses.list_for_owner("u1") == []


def test_customer_addresses_keep_one_active_default_per_owner(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "default.db")
    unit.initialize()
    with unit.transaction():
        unit.users.create(UserRecord(user_id="u1", email="u1@example.com", display_name="One", password_hash="x", role="customer"))
    base = dict(owner_user_id="u1", recipient_name="Alice", phone="13800000000", address1="1 Main St", city="Austin", state="TX", country="USA", zip="78701")
    with unit.transaction():
        unit.customer_addresses.create(CustomerAddressRecord(address_id="a1", is_default=True, **base))
        unit.customer_addresses.create(CustomerAddressRecord(address_id="a2", is_default=False, **base))
        unit.customer_addresses.set_default_for_owner("a2", "u1")

    addresses = unit.customer_addresses.list_for_owner("u1")
    assert [(item.address_id, item.is_default) for item in addresses] == [("a2", True), ("a1", False)]
