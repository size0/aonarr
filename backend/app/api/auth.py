from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.core.errors import api_error
from app.core.security import new_token, verify_admin_password
from app.core.store import store
from app.models.schemas import LoginRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginRequest) -> dict[str, dict[str, str]]:
    if payload.username != "admin" or not verify_admin_password(payload.password):
        raise api_error(401, "invalid_credentials", "Username or password is incorrect")
    token = new_token()
    store.create_session(token, payload.username)
    return {"data": {"token": token, "token_type": "bearer"}}


@router.post("/logout")
def logout(admin: dict[str, str] = Depends(require_admin)) -> dict[str, dict[str, bool]]:
    store.delete_session(admin["token"])
    return {"data": {"ok": True}}


@router.get("/me")
def me(admin: dict[str, str] = Depends(require_admin)) -> dict[str, dict[str, str]]:
    return {"data": {"username": admin["username"], "role": "admin"}}
