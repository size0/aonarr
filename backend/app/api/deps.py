from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import api_error
from app.core.store import store

bearer_scheme = HTTPBearer(auto_error=False)


def get_bearer_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str | None:
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    return None


def get_sse_token(request: Request) -> str | None:
    return request.query_params.get("sse_token")


def require_session(token: str | None, token_type: str) -> dict[str, str]:
    if not token:
        raise api_error(401, "unauthorized", "Missing authentication token")
    session = store.get_session(token)
    if not session:
        raise api_error(401, "unauthorized", "Invalid or expired authentication token")
    if session.get("token_type") != token_type:
        raise api_error(401, "unauthorized", "Invalid authentication token type")
    return {"username": session["username"], "token": token}


def require_admin(token: str | None = Depends(get_bearer_token)) -> dict[str, str]:
    return require_session(token, "bearer")


def require_sse_admin(token: str | None = Depends(get_sse_token)) -> dict[str, str]:
    return require_session(token, "sse")
