from time import monotonic

from fastapi import APIRouter, Depends, Request

from app.api.deps import require_admin
from app.core.config import get_settings
from app.core.errors import api_error
from app.core.security import new_token, utc_after, verify_admin_password
from app.core.store import store
from app.models.schemas import LoginRequest

router = APIRouter(prefix="/auth", tags=["auth"])
login_attempts: dict[str, list[float]] = {}


def check_login_rate_limit(key: str) -> None:
    settings = get_settings()
    now = monotonic()
    window_start = now - settings.login_rate_limit_window_seconds
    attempts = [attempt for attempt in login_attempts.get(key, []) if attempt >= window_start]
    if len(attempts) >= settings.login_rate_limit_max_attempts:
        login_attempts[key] = attempts
        raise api_error(429, "rate_limited", "Too many login attempts")
    attempts.append(now)
    login_attempts[key] = attempts


@router.post("/login")
def login(payload: LoginRequest, request: Request) -> dict[str, dict[str, str]]:
    settings = get_settings()
    client_host = request.client.host if request.client else "unknown"
    rate_limit_key = f"{client_host}:{payload.username}"
    check_login_rate_limit(rate_limit_key)
    if payload.username != settings.admin_username or not verify_admin_password(payload.password):
        raise api_error(401, "invalid_credentials", "Username or password is incorrect")
    login_attempts.pop(rate_limit_key, None)
    token = new_token()
    expires_at = utc_after(settings.admin_session_ttl_seconds)
    store.create_session(token, payload.username, expires_at, "bearer")
    return {"data": {"token": token, "token_type": "bearer", "expires_at": expires_at}}


@router.post("/sse-token")
def create_sse_token(admin: dict[str, str] = Depends(require_admin)) -> dict[str, dict[str, str]]:
    settings = get_settings()
    token = new_token()
    expires_at = utc_after(settings.sse_token_ttl_seconds)
    store.create_session(token, admin["username"], expires_at, "sse")
    return {"data": {"token": token, "token_type": "sse", "expires_at": expires_at}}


@router.post("/logout")
def logout(admin: dict[str, str] = Depends(require_admin)) -> dict[str, dict[str, bool]]:
    store.delete_session(admin["token"])
    return {"data": {"ok": True}}


@router.get("/me")
def me(admin: dict[str, str] = Depends(require_admin)) -> dict[str, dict[str, str]]:
    return {"data": {"username": admin["username"], "role": "admin"}}
