from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Cookie, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import COOKIE_NAME
from app.auth.models import AuthenticatedUser
from app.auth.service import (
    AuthService,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
)


class DeveloperIndex(BaseModel):
    developers: list[AuthenticatedUser]


class CreateDeveloperRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=100)
    temporary_password: str = Field(min_length=1, max_length=256)


class DeveloperStatusRequest(BaseModel):
    status: str


def create_admin_router(get_auth_service: Callable[[], AuthService]) -> APIRouter:
    router = APIRouter(prefix="/api/v1/admin/developers", tags=["admin"])

    def actor(
        token: str | None = Cookie(default=None, alias=COOKIE_NAME),
        service: AuthService = Depends(get_auth_service),
    ) -> AuthenticatedUser:
        try:
            user = service.authenticate(token)
            service.require_password_changed(user)
            if user.role != "developer":
                raise AuthorizationError("需要开发人员权限。")
            return user
        except AuthenticationError as exc:
            raise _error(401, "authentication_required", str(exc))
        except AuthorizationError as exc:
            raise _error(403, "forbidden", str(exc))

    @router.get("", response_model=DeveloperIndex)
    @router.get("/", response_model=DeveloperIndex, include_in_schema=False)
    def list_developers(
        current: AuthenticatedUser = Depends(actor),
        service: AuthService = Depends(get_auth_service),
    ) -> DeveloperIndex:
        return DeveloperIndex(developers=service.list_developers(current))

    @router.post("", status_code=201, response_model=AuthenticatedUser)
    def create_developer(
        request: CreateDeveloperRequest,
        current: AuthenticatedUser = Depends(actor),
        service: AuthService = Depends(get_auth_service),
    ) -> AuthenticatedUser:
        try:
            return service.create_developer(
                current,
                email=request.email,
                display_name=request.display_name,
                temporary_password=request.temporary_password,
            )
        except ConflictError as exc:
            raise _error(409, "account_conflict", str(exc))
        except ValueError as exc:
            raise _error(422, "invalid_account", str(exc))

    @router.patch("/{user_id}/status", response_model=AuthenticatedUser)
    def set_status(
        user_id: str,
        request: DeveloperStatusRequest,
        current: AuthenticatedUser = Depends(actor),
        service: AuthService = Depends(get_auth_service),
    ) -> AuthenticatedUser:
        try:
            return service.set_developer_status(current, user_id, request.status)
        except KeyError:
            raise _error(404, "not_found", "未找到开发人员账户。")
        except ConflictError as exc:
            raise _error(409, "account_conflict", str(exc))
        except ValueError as exc:
            raise _error(422, "invalid_status", str(exc))

    return router


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "recoverable": True},
    )
