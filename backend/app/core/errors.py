from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


def api_error(status_code: int, code: str, message: str, details: list[dict[str, Any]] | None = None) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "details": details or []},
    )


async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail), "details": []}},
    )


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Internal server error",
                "details": [],
            }
        },
    )
