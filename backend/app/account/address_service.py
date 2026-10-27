from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.auth.models import AuthenticatedUser
from app.persistence.models import CustomerAddressRecord
from app.persistence.sqlite import SqliteUnitOfWork
from app.tools.retail_port import RetailToolPort


class AddressNotFoundError(LookupError):
    pass


class AddressConflictError(ValueError):
    pass


class CustomerAddressService:
    def __init__(self, unit: SqliteUnitOfWork, retail_port: RetailToolPort) -> None:
        self._unit = unit
        self._retail_port = retail_port

    def list(self, actor: AuthenticatedUser) -> list[CustomerAddressRecord]:
        self._require_customer(actor)
        records = self._unit.customer_addresses.list_for_owner(actor.user_id)
        if records or not actor.retail_user_id:
            return records
        result = self._retail_port.call_tool(
            "get_user_details", {"user_id": actor.retail_user_id}, call_id="address-book-import"
        )
        if result.error or not isinstance(result.content, dict):
            return []
        address = result.content.get("address") or {}
        name = result.content.get("name") or {}
        recipient = " ".join(
            filter(None, [str(name.get("first_name", "")).strip(), str(name.get("last_name", "")).strip()])
        ) or actor.display_name
        imported = {**address, "recipient_name": recipient, "phone": ""}
        record = CustomerAddressRecord(
            address_id=str(uuid4()), owner_user_id=actor.user_id,
            is_default=True, **self._normalize(imported, require_phone=False),
        )
        with self._unit.transaction():
            self._unit.customer_addresses.create(record)
        return [record]

    def get(self, actor: AuthenticatedUser, address_id: str) -> CustomerAddressRecord:
        self._require_customer(actor)
        record = self._unit.customer_addresses.get_for_owner(address_id, actor.user_id)
        if not record:
            raise AddressNotFoundError("地址不存在。")
        return record

    def create(self, actor: AuthenticatedUser, **payload: str) -> CustomerAddressRecord:
        existing = self.list(actor)
        record = CustomerAddressRecord(
            address_id=str(uuid4()), owner_user_id=actor.user_id,
            is_default=not existing, **self._normalize(payload, require_phone=True),
        )
        if record.is_default:
            self._sync(actor, record)
        with self._unit.transaction():
            self._unit.customer_addresses.create(record)
        return record

    def update(self, actor: AuthenticatedUser, address_id: str, **payload: str) -> CustomerAddressRecord:
        current = self.get(actor, address_id)
        updated = current.model_copy(update={
            **self._normalize(payload, require_phone=True),
            "updated_at": datetime.now(timezone.utc),
        })
        if updated.is_default:
            self._sync(actor, updated)
        with self._unit.transaction():
            self._unit.customer_addresses.update(updated)
        return updated

    def archive(self, actor: AuthenticatedUser, address_id: str) -> None:
        record = self.get(actor, address_id)
        if record.is_default:
            raise AddressConflictError("默认地址不能删除，请先设置其他默认地址。")
        with self._unit.transaction():
            self._unit.customer_addresses.archive_for_owner(address_id, actor.user_id)

    def set_default(self, actor: AuthenticatedUser, address_id: str) -> CustomerAddressRecord:
        record = self.get(actor, address_id)
        if not record.phone:
            raise AddressConflictError("请先补充收货人电话。")
        self._sync(actor, record)
        with self._unit.transaction():
            self._unit.customer_addresses.set_default_for_owner(address_id, actor.user_id)
        return self.get(actor, address_id)

    def _sync(self, actor: AuthenticatedUser, record: CustomerAddressRecord) -> None:
        if not actor.retail_user_id:
            raise AddressConflictError("当前账户尚未关联购买账户。")
        address = {
            key: getattr(record, key)
            for key in ("address1", "address2", "city", "state", "country", "zip")
        }
        result = self._retail_port.call_tool(
            "modify_user_address", {"user_id": actor.retail_user_id, **address},
            call_id="address-book-default-sync",
        )
        if result.error:
            raise AddressConflictError("默认地址同步失败，请稍后重试。")

    @staticmethod
    def _normalize(payload: dict, *, require_phone: bool) -> dict[str, str]:
        keys = ("recipient_name", "phone", "address1", "address2", "city", "state", "country", "zip")
        data = {key: str(payload.get(key, "")).strip() for key in keys}
        required = ("recipient_name", "address1", "city", "state", "country", "zip")
        if require_phone:
            required += ("phone",)
        if any(not data[key] for key in required):
            raise AddressConflictError("请填写完整的收货地址。")
        digits = data["phone"].replace("+", "", 1)
        if data["phone"] and (not digits.isdigit() or len(digits) < 7):
            raise AddressConflictError("请输入有效的收货人电话。")
        return data

    @staticmethod
    def _require_customer(actor: AuthenticatedUser) -> None:
        if actor.role != "customer":
            raise AddressConflictError("只有客户可以管理收货地址。")
