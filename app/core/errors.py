"""Typed application errors and the single error envelope returned by the API.

Every error response has the shape ``{"error": {"code": "...", "message": "..."}}``.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Base class for business errors that map to an HTTP status."""

    status_code: int = 400

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    """Invalid state transition, consumed token, duplicate execution."""

    status_code = 409


class UnprocessableError(AppError):
    status_code = 422


class UpstreamError(AppError):
    """PayPal or LLM failure that did not change any persisted state."""

    status_code = 502


def error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    """Build the canonical error envelope."""
    return {"error": {"code": code, "message": message}}


async def _handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))


async def _handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    details = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()
    )
    return JSONResponse(
        status_code=422, content=error_body("VALIDATION_ERROR", details[:500] or "Invalid request")
    )


async def _handle_http_exception(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(f"HTTP_{exc.status_code}", str(exc.detail)),
        headers=getattr(exc, "headers", None),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the handlers that enforce the error envelope."""
    app.add_exception_handler(AppError, _handle_app_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)  # type: ignore[arg-type]