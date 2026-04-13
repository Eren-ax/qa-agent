import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("app")


class ExceptionLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal Server Error"},
            )


async def request_validation_exception_handler(_: Request, exc: RequestValidationError):
    detail = str(exc.errors())
    return JSONResponse(
        status_code=400,
        content={"detail": detail},
    )


async def response_validation_exception_handler(_: Request, exc: ResponseValidationError):
    detail = str(exc.errors())
    return JSONResponse(
        status_code=400,
        content={"detail": detail},
    )
