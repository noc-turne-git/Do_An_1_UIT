import logging
from time import monotonic
from uuid import uuid4
from contextlib import asynccontextmanager

from sqlalchemy.exc import SQLAlchemyError
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.health import router
from app.api.chat import router as chat_router
from app.api.dev_workflows import router as dev_workflows_router
from app.api.workflows import router as workflows_router
from app.core.config import Settings, get_settings
from shared.errors import ApplicationError
from app.core.logging import configure_logging
from app.db.session import Database

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.database = Database(settings)
        logger.info("API started; database configured: %s", settings.database_url is not None)
        try:
            yield
        finally:
            app.state.database.dispose()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.include_router(router)
    app.include_router(chat_router)
    app.include_router(dev_workflows_router)
    app.include_router(workflows_router)

    @app.middleware('http')
    async def request_log(request: Request, call_next):
        request_id = str(uuid4())
        request.state.request_id = request_id
        started = monotonic()
        response = await call_next(request)
        response.headers['X-Request-ID'] = request_id
        route = request.scope.get('route')
        logger.info('http.request request_id=%s method=%s route=%s status=%s duration_ms=%.1f',
                    request_id, request.method, getattr(route, 'path', 'unmatched'),
                    response.status_code, (monotonic() - started) * 1000)
        return response

    @app.exception_handler(ApplicationError)
    async def application_error(request: Request, exc: ApplicationError):
        return JSONResponse(status_code=404 if exc.code == 'not_found' else 503 if exc.retryable else 400,
                            content={"error": {"code": exc.code, "message": exc.message, "retryable": exc.retryable}})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Request validation failed"}})

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, headers=exc.headers,
                            content={"error": {"code": "http_error", "message": str(exc.detail)}})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logger.error("Database operation failed: %s", type(exc).__name__)
        return JSONResponse(status_code=503, content={"error": {
            "code": "database_error", "message": "Database operation failed", "retryable": True}})

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        # Do not log exception payloads: connection strings/prompts may contain secrets.
        logger.error("Unhandled error: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "Internal server error"}})

    return app


app = create_app()
