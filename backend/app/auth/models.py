from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AuthenticatedUser(BaseModel):
    user_id: str
    email: str
    display_name: str
    role: Literal["customer", "developer"]
    status: Literal["active", "disabled"]
    must_change_password: bool
    retail_user_id: str | None = None


class PublicAuthenticatedUser(BaseModel):
    user_id: str
    email: str
    display_name: str
    role: Literal["customer", "developer"]
    status: Literal["active", "disabled"]
    must_change_password: bool
    retail_account_linked: bool

    @classmethod
    def from_user(cls, user: AuthenticatedUser) -> PublicAuthenticatedUser:
        return cls(
            user_id=user.user_id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            status=user.status,
            must_change_password=user.must_change_password,
            retail_account_linked=user.retail_user_id is not None,
        )


class IssuedSession(BaseModel):
    user: AuthenticatedUser
    raw_token: str
    expires_at: datetime

