from __future__ import annotations

from datetime import datetime, timedelta, timezone
from collections.abc import Callable
import hashlib
import secrets
import sqlite3
from typing import Any
from uuid import uuid4

from app.auth.models import AuthenticatedUser, IssuedSession
from app.auth.passwords import hash_password, verify_password
from app.persistence.models import (
    AuthAuditEventRecord,
    AuthSessionRecord,
    UserRecord,
)
from app.persistence.sqlite import SqliteUnitOfWork
from app.tools.retail_port import RetailToolPort
from app.account.address_service import CustomerAddressService
from app.account.spending import SpendingService
from app.orders.service import OrderCenterService


class AuthenticationError(ValueError):
    pass


class AuthorizationError(PermissionError):
    pass


class ConflictError(ValueError):
    pass


class PasswordChangeRequired(PermissionError):
    pass


class RetailProfileError(RuntimeError):
    pass


class AuthService:
    def __init__(
        self,
        unit: SqliteUnitOfWork,
        session_hours: int = 12,
        retail_identity_resolver: Callable[[str], str | None] | None = None,
        retail_tool_port: RetailToolPort | None = None,
    ) -> None:
        self._unit = unit
        self._session_hours = session_hours
        self._retail_identity_resolver = retail_identity_resolver
        self._retail_tool_port = retail_tool_port
        self.addresses = CustomerAddressService(unit, retail_tool_port) if retail_tool_port else None
        self.spending = SpendingService(unit, retail_tool_port) if retail_tool_port else None
        self.orders = OrderCenterService(unit, retail_tool_port) if retail_tool_port else None

    @staticmethod
    def token_hash(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    def register_customer(
        self, *, email: str, display_name: str, password: str
    ) -> IssuedSession:
        normalized_email = _email(email)
        retail_user_id = (
            self._retail_identity_resolver(normalized_email)
            if self._retail_identity_resolver is not None
            else None
        )
        if self._retail_identity_resolver is not None and retail_user_id is None:
            raise AuthenticationError("未找到与该邮箱对应的购买账户。")
        record = UserRecord(
            user_id=str(uuid4()),
            email=normalized_email,
            display_name=_display_name(display_name),
            password_hash=hash_password(password),
            role="customer",
            retail_user_id=retail_user_id,
        )
        try:
            with self._unit.transaction():
                self._unit.users.create(record)
                self._audit(record.user_id, "customer.registered", {"email": record.email})
                issued = self._issue(record)
        except sqlite3.IntegrityError as exc:
            raise ConflictError("该邮箱已注册。") from exc
        return issued

    def login(self, *, email: str, password: str) -> IssuedSession:
        record = self._unit.users.get_by_email(email)
        if (
            record is None
            or record.status != "active"
            or not verify_password(password, record.password_hash)
        ):
            with self._unit.transaction():
                self._audit(
                    record.user_id if record else None,
                    "login.failed",
                    {"email": _email(email)},
                )
            raise AuthenticationError("邮箱或密码不正确。")
        record = self._ensure_retail_identity(record)
        now = datetime.now(timezone.utc)
        record = record.model_copy(update={"last_login_at": now, "updated_at": now})
        with self._unit.transaction():
            self._unit.users.update(record)
            self._audit(record.user_id, "login.succeeded")
            issued = self._issue(record)
        return issued

    def authenticate(self, raw_token: str | None) -> AuthenticatedUser:
        if not raw_token:
            raise AuthenticationError("请先登录。")
        session = self._unit.auth_sessions.get_by_token_hash(self.token_hash(raw_token))
        now = datetime.now(timezone.utc)
        if session is None or session.revoked_at is not None or session.expires_at <= now:
            raise AuthenticationError("登录状态已失效，请重新登录。")
        user = self._unit.users.get(session.user_id)
        if user is None or user.status != "active":
            raise AuthenticationError("登录状态已失效，请重新登录。")
        if (
            user.role == "customer"
            and user.retail_user_id is None
            and self._retail_identity_resolver is not None
        ):
            raise AuthenticationError("购买账户尚未绑定，请重新登录。")
        return _public(user)

    def require_password_changed(self, user: AuthenticatedUser) -> None:
        if user.must_change_password:
            raise PasswordChangeRequired("首次登录需要修改密码。")

    def logout(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        session = self._unit.auth_sessions.get_by_token_hash(self.token_hash(raw_token))
        if session is None:
            return
        with self._unit.transaction():
            self._unit.auth_sessions.revoke(session.session_id)
            self._audit(session.user_id, "logout")

    def change_password(
        self, raw_token: str, *, current_password: str, new_password: str
    ) -> IssuedSession:
        current = self.authenticate(raw_token)
        record = self._unit.users.get(current.user_id)
        if record is None or not verify_password(current_password, record.password_hash):
            raise AuthenticationError("当前密码不正确。")
        now = datetime.now(timezone.utc)
        record = record.model_copy(
            update={
                "password_hash": hash_password(new_password),
                "must_change_password": False,
                "updated_at": now,
            }
        )
        with self._unit.transaction():
            self._unit.users.update(record)
            self._unit.auth_sessions.revoke_all_for_user(record.user_id)
            self._audit(record.user_id, "password.changed")
            issued = self._issue(record)
        return issued

    def update_profile(
        self,
        actor: AuthenticatedUser,
        *,
        display_name: str,
    ) -> AuthenticatedUser:
        if actor.role != "customer":
            raise AuthorizationError("只有客户可以修改此资料。")
        record = self._unit.users.get(actor.user_id)
        if record is None or record.status != "active":
            raise AuthenticationError("登录状态已失效，请重新登录。")
        updated = record.model_copy(
            update={
                "display_name": _display_name(display_name),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        with self._unit.transaction():
            self._unit.users.update(updated)
            self._audit(updated.user_id, "customer.profile_updated")
        return _public(updated)

    def get_retail_address(self, actor: AuthenticatedUser) -> dict[str, str]:
        retail_user_id = self._require_retail_customer(actor)
        result = self._retail_tool_port.call_tool(
            "get_user_details",
            {"user_id": retail_user_id},
            call_id="account-address-read",
        )
        if result.error or not isinstance(result.content, dict):
            raise RetailProfileError("暂时无法读取收货地址。")
        return _address(result.content.get("address"))

    def update_retail_address(
        self, actor: AuthenticatedUser, *, address: dict[str, str]
    ) -> dict[str, str]:
        retail_user_id = self._require_retail_customer(actor)
        normalized = _address(address)
        result = self._retail_tool_port.call_tool(
            "modify_user_address",
            {"user_id": retail_user_id, **normalized},
            call_id="account-address-update",
        )
        if result.error:
            raise RetailProfileError("保存地址失败，请稍后重试。")
        with self._unit.transaction():
            self._audit(actor.user_id, "customer.address_updated")
        return normalized

    def _require_retail_customer(self, actor: AuthenticatedUser) -> str:
        if actor.role != "customer":
            raise AuthorizationError("只有客户可以管理收货地址。")
        if actor.retail_user_id is None:
            raise RetailProfileError("当前账户尚未关联购买账户。")
        if self._retail_tool_port is None:
            raise RetailProfileError("收货地址服务尚未配置。")
        return actor.retail_user_id

    def list_developers(self, actor: AuthenticatedUser) -> list[AuthenticatedUser]:
        self._require_developer(actor)
        return [_public(user) for user in self._unit.users.list_developers()]

    def create_developer(
        self,
        actor: AuthenticatedUser,
        *,
        email: str,
        display_name: str,
        temporary_password: str,
    ) -> AuthenticatedUser:
        self._require_developer(actor)
        record = UserRecord(
            user_id=str(uuid4()),
            email=_email(email),
            display_name=_display_name(display_name),
            password_hash=hash_password(temporary_password),
            role="developer",
            must_change_password=True,
            created_by_user_id=actor.user_id,
        )
        try:
            with self._unit.transaction():
                self._unit.users.create(record)
                self._audit(record.user_id, "developer.created", {"created_by": actor.user_id})
        except sqlite3.IntegrityError as exc:
            raise ConflictError("该邮箱已注册。") from exc
        return _public(record)

    def set_developer_status(
        self,
        actor: AuthenticatedUser,
        user_id: str,
        status: str,
    ) -> AuthenticatedUser:
        self._require_developer(actor)
        if status not in {"active", "disabled"}:
            raise ValueError("无效的账户状态。")
        target = self._unit.users.get(user_id)
        if target is None or target.role != "developer":
            raise KeyError(user_id)
        if status == "disabled" and target.user_id == actor.user_id:
            raise ConflictError("不能禁用当前登录账户。")
        active = [user for user in self._unit.users.list_developers() if user.status == "active"]
        if status == "disabled" and target.status == "active" and len(active) <= 1:
            raise ConflictError("至少需要保留一个有效开发人员账户。")
        now = datetime.now(timezone.utc)
        target = target.model_copy(update={"status": status, "updated_at": now})
        with self._unit.transaction():
            self._unit.users.update(target)
            if status == "disabled":
                self._unit.auth_sessions.revoke_all_for_user(target.user_id)
            self._audit(
                target.user_id,
                "developer.status_changed",
                {"status": status, "changed_by": actor.user_id},
            )
        return _public(target)

    def _issue(self, record: UserRecord) -> IssuedSession:
        raw_token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=self._session_hours)
        self._unit.auth_sessions.create(
            AuthSessionRecord(
                session_id=str(uuid4()),
                user_id=record.user_id,
                token_hash=self.token_hash(raw_token),
                created_at=now,
                expires_at=expires_at,
                last_seen_at=now,
            )
        )
        return IssuedSession(user=_public(record), raw_token=raw_token, expires_at=expires_at)

    def _ensure_retail_identity(self, record: UserRecord) -> UserRecord:
        if (
            record.role != "customer"
            or record.retail_user_id is not None
            or self._retail_identity_resolver is None
        ):
            return record
        retail_user_id = self._retail_identity_resolver(record.email)
        if retail_user_id is None:
            raise AuthenticationError("未找到与该邮箱对应的购买账户。")
        linked = record.model_copy(
            update={
                "retail_user_id": retail_user_id,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        try:
            with self._unit.transaction():
                self._unit.users.update(linked)
                self._audit(
                    linked.user_id,
                    "customer.retail_identity_linked",
                    {"retail_user_id": retail_user_id},
                )
        except sqlite3.IntegrityError as exc:
            raise AuthenticationError("该购买账户已绑定到其他登录账户。") from exc
        return linked

    def _audit(
        self, user_id: str | None, event_type: str, payload: dict | None = None
    ) -> None:
        self._unit.auth_audit_events.append(
            AuthAuditEventRecord(
                event_id=str(uuid4()),
                user_id=user_id,
                event_type=event_type,
                payload=payload or {},
            )
        )

    @staticmethod
    def _require_developer(actor: AuthenticatedUser) -> None:
        if actor.role != "developer" or actor.status != "active":
            raise AuthorizationError("需要开发人员权限。")


def _email(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError("请输入有效邮箱。")
    return normalized


def _display_name(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("请输入姓名。")
    return normalized


def _address(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise RetailProfileError("收货地址数据无效。")
    required = ("address1", "city", "state", "country", "zip")
    normalized = {
        key: str(value.get(key, "")).strip()
        for key in ("address1", "address2", "city", "state", "country", "zip")
    }
    if any(not normalized[key] for key in required):
        raise RetailProfileError("请填写完整的收货地址。")
    return normalized


def _public(record: UserRecord) -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=record.user_id,
        email=record.email,
        display_name=record.display_name,
        role=record.role,
        status=record.status,
        must_change_password=record.must_change_password,
        retail_user_id=record.retail_user_id,
    )
