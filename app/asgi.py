"""Application implementation - ASGI."""

import os
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.config import config
from app.controllers import base
from app.models.exception import HttpException
from app.router import root_api_router
from app.utils import utils


@asynccontextmanager
async def application_lifespan(_: FastAPI):
    """集中处理 API 进程启动恢复和关闭日志。"""
    logger.info("startup event")

    # StaticFiles mounts are configured without import-time filesystem checks.
    # Create their backing directories only when the application actually starts.
    utils.task_dir()
    utils.public_dir()

    configured_api_key = config.app.get("api_key", "")
    if configured_api_key in (None, ""):
        logger.warning(
            "API key authentication is disabled; keep the API on a trusted network"
        )
    elif isinstance(configured_api_key, str):
        # 只记录保护范围，不得输出 Key、长度或摘要，避免凭据进入日志系统。
        logger.info("API key authentication is enabled for /api/v1 and /tasks")
    else:
        logger.error(
            "API key authentication is misconfigured: app.api_key must be a string"
        )

    # 跨平台发布由当前进程线程池执行，不会在服务重启后恢复。启动时把 Redis
    # 中确认已失去执行进程的活动状态收敛为失败，避免任务永久无法删除。
    from app.services import task as task_service

    task_service.recover_interrupted_cross_posts()
    try:
        yield
    finally:
        logger.info("shutdown event")


def exception_handler(request: Request, e: HttpException):
    return JSONResponse(
        status_code=e.status_code,
        content=utils.get_response(e.status_code, e.data, e.message),
    )


def validation_exception_handler(request: Request, e: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content=utils.get_response(
            status=400, data=e.errors(), message="field required"
        ),
    )


def parse_cors_allowed_origins(raw_origins: str | None) -> list[str]:
    """Parse the explicit browser cross-origin allowlist.

    CORS applies to browser JavaScript only. Server-side clients without an Origin
    header (curl, Postman, n8n, SDKs) remain compatible. An empty configuration
    means no cross-origin browser access: normal same-origin requests still work.
    """
    if not raw_origins:
        return []
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


def configure_cors(instance: FastAPI, allowed_origins: list[str]) -> None:
    """Configure CORS only when the user explicitly supplied trusted origins."""
    if not allowed_origins:
        logger.info(
            "browser cross-origin API access is disabled; set "
            "CORS_ALLOWED_ORIGINS to enable trusted origins"
        )
        return

    allow_all_origins = "*" in allowed_origins
    configured_api_key = config.app.get("api_key", "")
    if allow_all_origins and configured_api_key in (None, ""):
        logger.warning(
            "CORS allows every browser origin while API key authentication is "
            "disabled; configure app.api_key or restrict CORS_ALLOWED_ORIGINS"
        )

    instance.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        # Never combine wildcard origin reflection with browser credentials.
        allow_credentials=not allow_all_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        # Exact allowlists may opt into modern Private Network Access preflights.
        # Wildcard mode deliberately does not expose private-network access.
        allow_private_network=not allow_all_origins,
    )


def is_browser_origin_allowed(
    request: Request, allowed_origins: list[str]
) -> bool:
    """Return True for server clients, same-origin browsers, or explicit allowlist."""
    origin = request.headers.get("origin")
    if not origin:
        return True
    if "*" in allowed_origins or origin in allowed_origins:
        return True

    request_url = urlsplit(str(request.url))
    request_origin = f"{request_url.scheme}://{request_url.netloc}"
    return origin == request_origin


def configure_browser_access(instance: FastAPI, allowed_origins: list[str]) -> None:
    """Apply active Origin rejection plus CORS response policy."""

    @instance.middleware("http")
    async def reject_untrusted_browser_origin(request: Request, call_next):
        if not is_browser_origin_allowed(request, allowed_origins):
            # Origin is navigation metadata, not a credential, but avoid echoing
            # arbitrary attacker-controlled strings into normal application logs.
            logger.warning(
                "blocked untrusted browser origin: "
                f"method={request.method}, path={request.url.path}"
            )
            return JSONResponse(
                status_code=403,
                content=utils.get_response(
                    status=403,
                    message="cross-origin browser request is not allowed",
                ),
            )
        return await call_next(request)

    # Register CORS last so trusted preflight requests are handled by Starlette;
    # actual simple requests still pass through the active Origin guard above.
    configure_cors(instance, allowed_origins)


def get_application() -> FastAPI:
    """Initialize FastAPI application."""
    instance = FastAPI(
        title=config.project_name,
        description=config.project_description,
        version=config.project_version,
        debug=False,
        lifespan=application_lifespan,
    )
    instance.include_router(root_api_router)
    instance.add_exception_handler(HttpException, exception_handler)
    instance.add_exception_handler(RequestValidationError, validation_exception_handler)
    return instance


app = get_application()


@app.middleware("http")
async def protect_generated_task_files(request: Request, call_next):
    """保护任务产物静态路由，防止绕过 API 鉴权直接下载。"""
    request_path = request.url.path
    is_task_file = request_path == "/tasks" or request_path.startswith("/tasks/")
    if is_task_file and request.method != "OPTIONS":
        try:
            base.verify_token(request)
        except HttpException as exception:
            return exception_handler(request, exception)

    return await call_next(request)


# MoneyPrinterTurbo v1.3.6 security policy, selectively backported while preserving
# Centinela's deferred StaticFiles directory creation behavior.
cors_allowed_origins = parse_cors_allowed_origins(
    os.getenv("CORS_ALLOWED_ORIGINS", "")
)
configure_browser_access(app, cors_allowed_origins)

task_dir = os.path.join(utils.storage_dir(), "tasks")
app.mount(
    "/tasks",
    StaticFiles(directory=task_dir, html=True, check_dir=False),
    name="",
)

public_dir = utils.resource_dir("public")
app.mount(
    "/",
    StaticFiles(directory=public_dir, html=True, check_dir=False),
    name="",
)
