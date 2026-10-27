from __future__ import annotations

import os
from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.auth.models import AuthenticatedUser, IssuedSession, PublicAuthenticatedUser
from app.auth.service import (
    AuthService,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    RetailProfileError,
)
from app.account.address_service import AddressConflictError, AddressNotFoundError
from app.operations.rate_limit import LoginRateLimiter


COOKIE_NAME = "ecom_session"


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class UpdateProfileRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class AddressPayload(BaseModel):
    address1: str = Field(min_length=1, max_length=200)
    address2: str = Field(default="", max_length=200)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    country: str = Field(min_length=1, max_length=100)
    zip: str = Field(min_length=1, max_length=30)


class AddressBookPayload(AddressPayload):
    recipient_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=7, max_length=30)


class AddressBookItem(AddressBookPayload):
    phone: str = Field(default="", max_length=30)
    address_id: str
    is_default: bool


class AuthResponse(BaseModel):
    user: PublicAuthenticatedUser
    redirect_to: str


def create_auth_router(
    get_auth_service: Callable[[], AuthService],
    get_login_limiter: Callable[[], LoginRateLimiter] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

    @router.post("/register", status_code=201, response_model=AuthResponse)
    def register(
        request: RegisterRequest,
        response: Response,
        service: AuthService = Depends(get_auth_service),
    ) -> AuthResponse:
        try:
            issued = service.register_customer(
                email=request.email,
                display_name=request.display_name,
                password=request.password,
            )
        except ConflictError as exc:
            raise _error(409, "email_conflict", str(exc))
        except ValueError as exc:
            raise _error(422, "invalid_registration", str(exc))
        _set_cookie(response, issued)
        return AuthResponse(user=PublicAuthenticatedUser.from_user(issued.user), redirect_to="/support/")

    @router.post("/login", response_model=AuthResponse)
    def login(
        request: LoginRequest,
        http_request: Request,
        response: Response,
        service: AuthService = Depends(get_auth_service),
    ) -> AuthResponse:
        limiter = get_login_limiter() if get_login_limiter is not None else None
        limiter_key = None
        if limiter is not None:
            client_ip = http_request.client.host if http_request.client else "unknown"
            limiter_key = limiter.key(client_ip, request.email)
            retry_after = limiter.retry_after(limiter_key)
            if retry_after is not None:
                raise HTTPException(
                    status_code=429,
                    detail={"code": "login_rate_limited", "message": "登录尝试过多，请稍后重试。", "recoverable": True},
                    headers={"Retry-After": str(retry_after)},
                )
        try:
            issued = service.login(email=request.email, password=request.password)
        except AuthenticationError as exc:
            if limiter is not None and limiter_key is not None:
                limiter.record_failure(limiter_key)
            raise _error(401, "invalid_credentials", str(exc))
        if limiter is not None and limiter_key is not None:
            limiter.record_success(limiter_key)
        _set_cookie(response, issued)
        return AuthResponse(user=PublicAuthenticatedUser.from_user(issued.user), redirect_to=_redirect(issued.user))

    @router.get("/me", response_model=PublicAuthenticatedUser)
    def me(
        token: str | None = Cookie(default=None, alias=COOKIE_NAME),
        service: AuthService = Depends(get_auth_service),
    ) -> PublicAuthenticatedUser:
        try:
            return PublicAuthenticatedUser.from_user(service.authenticate(token))
        except AuthenticationError as exc:
            raise _error(401, "authentication_required", str(exc))

    @router.patch("/me", response_model=PublicAuthenticatedUser)
    def update_profile(
        payload: UpdateProfileRequest,
        token: str | None = Cookie(default=None, alias=COOKIE_NAME),
        service: AuthService = Depends(get_auth_service),
    ) -> PublicAuthenticatedUser:
        try:
            actor = service.authenticate(token)
            return PublicAuthenticatedUser.from_user(
                service.update_profile(actor, display_name=payload.display_name)
            )
        except AuthenticationError as exc:
            raise _error(401, "authentication_required", str(exc))
        except AuthorizationError as exc:
            raise _error(403, "forbidden", str(exc))
        except ValueError as exc:
            raise _error(422, "invalid_profile", str(exc))

    @router.get("/address", response_model=AddressPayload)
    def get_address(
        token: str | None = Cookie(default=None, alias=COOKIE_NAME),
        service: AuthService = Depends(get_auth_service),
    ) -> AddressPayload:
        try:
            actor = service.authenticate(token)
            return AddressPayload(**service.get_retail_address(actor))
        except AuthenticationError as exc:
            raise _error(401, "authentication_required", str(exc))
        except AuthorizationError as exc:
            raise _error(403, "forbidden", str(exc))
        except RetailProfileError as exc:
            raise _error(409, "retail_profile_unavailable", str(exc))

    @router.put("/address", response_model=AddressPayload)
    def update_address(
        payload: AddressPayload,
        token: str | None = Cookie(default=None, alias=COOKIE_NAME),
        service: AuthService = Depends(get_auth_service),
    ) -> AddressPayload:
        try:
            actor = service.authenticate(token)
            return AddressPayload(
                **service.update_retail_address(actor, address=payload.model_dump())
            )
        except AuthenticationError as exc:
            raise _error(401, "authentication_required", str(exc))
        except AuthorizationError as exc:
            raise _error(403, "forbidden", str(exc))
        except RetailProfileError as exc:
            raise _error(409, "retail_profile_unavailable", str(exc))

    def address_service(service: AuthService):
        if service.addresses is None:
            raise _error(409, "retail_profile_unavailable", "收货地址服务尚未配置。")
        return service.addresses

    @router.get("/addresses", response_model=list[AddressBookItem])
    def list_addresses(
        token: str | None = Cookie(default=None, alias=COOKIE_NAME),
        service: AuthService = Depends(get_auth_service),
    ) -> list[AddressBookItem]:
        actor = _actor(token, service)
        return [AddressBookItem(**item.model_dump()) for item in address_service(service).list(actor)]

    @router.post("/addresses", status_code=201, response_model=AddressBookItem)
    def create_address(
        payload: AddressBookPayload,
        token: str | None = Cookie(default=None, alias=COOKIE_NAME),
        service: AuthService = Depends(get_auth_service),
    ) -> AddressBookItem:
        actor = _actor(token, service)
        try:
            return AddressBookItem(**address_service(service).create(actor, **payload.model_dump()).model_dump())
        except AddressConflictError as exc:
            raise _error(409, "address_conflict", str(exc))

    @router.get("/addresses/{address_id}", response_model=AddressBookItem)
    def get_address_item(
        address_id: str,
        token: str | None = Cookie(default=None, alias=COOKIE_NAME),
        service: AuthService = Depends(get_auth_service),
    ) -> AddressBookItem:
        try:
            return AddressBookItem(**address_service(service).get(_actor(token, service), address_id).model_dump())
        except AddressNotFoundError as exc:
            raise _error(404, "address_not_found", str(exc))

    @router.put("/addresses/{address_id}", response_model=AddressBookItem)
    def update_address_item(
        address_id: str, payload: AddressBookPayload,
        token: str | None = Cookie(default=None, alias=COOKIE_NAME),
        service: AuthService = Depends(get_auth_service),
    ) -> AddressBookItem:
        try:
            item = address_service(service).update(_actor(token, service), address_id, **payload.model_dump())
            return AddressBookItem(**item.model_dump())
        except AddressNotFoundError as exc:
            raise _error(404, "address_not_found", str(exc))
        except AddressConflictError as exc:
            raise _error(409, "address_conflict", str(exc))

    @router.delete("/addresses/{address_id}", status_code=204)
    def delete_address_item(
        address_id: str,
        token: str | None = Cookie(default=None, alias=COOKIE_NAME),
        service: AuthService = Depends(get_auth_service),
    ) -> None:
        try:
            address_service(service).archive(_actor(token, service), address_id)
        except AddressNotFoundError as exc:
            raise _error(404, "address_not_found", str(exc))
        except AddressConflictError as exc:
            raise _error(409, "address_conflict", str(exc))

    @router.post("/addresses/{address_id}/default", response_model=AddressBookItem)
    def set_default_address(
        address_id: str,
        token: str | None = Cookie(default=None, alias=COOKIE_NAME),
        service: AuthService = Depends(get_auth_service),
    ) -> AddressBookItem:
        try:
            item = address_service(service).set_default(_actor(token, service), address_id)
            return AddressBookItem(**item.model_dump())
        except AddressNotFoundError as exc:
            raise _error(404, "address_not_found", str(exc))
        except AddressConflictError as exc:
            raise _error(409, "address_conflict", str(exc))

    @router.get("/spending")
    def spending_summary(
        period: Literal["week", "month", "year"] = "month",
        token: str | None = Cookie(default=None, alias=COOKIE_NAME),
        service: AuthService = Depends(get_auth_service),
    ) -> dict:
        actor = _actor(token, service)
        if service.spending is None:
            raise _error(409, "retail_profile_unavailable", "消费统计服务尚未配置。")
        return service.spending.summary(actor, period)

    @router.post("/change-password", response_model=AuthResponse)
    def change_password(
        request: ChangePasswordRequest,
        response: Response,
        token: str | None = Cookie(default=None, alias=COOKIE_NAME),
        service: AuthService = Depends(get_auth_service),
    ) -> AuthResponse:
        try:
            issued = service.change_password(
                token or "",
                current_password=request.current_password,
                new_password=request.new_password,
            )
        except AuthenticationError as exc:
            raise _error(401, "invalid_credentials", str(exc))
        except ValueError as exc:
            raise _error(422, "invalid_password", str(exc))
        _set_cookie(response, issued)
        return AuthResponse(user=PublicAuthenticatedUser.from_user(issued.user), redirect_to=_redirect(issued.user))

    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
    def logout(
        response: Response,
        token: str | None = Cookie(default=None, alias=COOKIE_NAME),
        service: AuthService = Depends(get_auth_service),
    ) -> None:
        service.logout(token)
        response.delete_cookie(COOKIE_NAME, path="/")

    return router


def _actor(token: str | None, service: AuthService) -> AuthenticatedUser:
    try:
        return service.authenticate(token)
    except AuthenticationError as exc:
        raise _error(401, "authentication_required", str(exc))


def _redirect(user: AuthenticatedUser) -> str:
    if user.must_change_password:
        return "/change-password/"
    return "/dashboard/" if user.role == "developer" else "/support/"


def _set_cookie(response: Response, issued: IssuedSession) -> None:
    response.set_cookie(
        COOKIE_NAME,
        issued.raw_token,
        httponly=True,
        samesite="lax",
        secure=os.getenv("ECOM_AUTH_COOKIE_SECURE", "false").lower() == "true",
        max_age=max(0, int((issued.expires_at.timestamp() - __import__("time").time()))),
        path="/",
    )


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "recoverable": status_code < 500},
    )
