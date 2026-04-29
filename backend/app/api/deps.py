from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import api_error
from app.core.store import store

bearer_scheme = HTTPBearer(auto_error=False)


def get_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str | None:
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    query_token = request.query_params.get("access_token")
    if query_token:
        return query_token
    return None


def require_admin(token: str | None = Depends(get_token)) -> dict[str, str]:
    if not token:
        raise api_error(401, "unauthorized", "Missing authentication token")
    session = store.get_session(token)
    if not session:
        raise api_error(401, "unauthorized", "Invalid or expired authentication token")
    return {"username": session["username"], "token": token}
