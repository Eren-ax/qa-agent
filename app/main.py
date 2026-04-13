import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from prometheus_fastapi_instrumentator import Instrumentator

from app.api import router
from app.config import app_config
from app.handler import (
    ExceptionLoggingMiddleware,
    request_validation_exception_handler,
    response_validation_exception_handler,
)


logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup events
    logger.info("Starting up...")

    yield

    # shutdown events
    logger.info("Shutting down...")


app = FastAPI(
    lifespan=lifespan,
    docs_url=app_config.docs_url,
    redoc_url=app_config.redoc_url,
)

# routes
app.include_router(router)

# middleware
app.add_middleware(ExceptionLoggingMiddleware)

# exception handlers
app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
app.add_exception_handler(ResponseValidationError, response_validation_exception_handler)

# prometheus
Instrumentator().instrument(app).expose(app)
