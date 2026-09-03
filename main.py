import uvicorn
from loguru import logger

from app.config import config


C3_LISTEN_HOST = "127.0.0.1"


if __name__ == "__main__":
    if config.listen_host != C3_LISTEN_HOST:
        logger.warning(
            f"C3 hardening overrides configured listen_host={config.listen_host!r}; "
            "binding to loopback only"
        )
    logger.info(
        "start server, docs: http://127.0.0.1:" + str(config.listen_port) + "/docs"
    )
    # FFmpeg 探测已经移到 app/services/task.py 的共享任务流水线里，这样
    # API、CLI 和 WebUI 三条路径都能统一覆盖，这里不再单独检查。
    uvicorn.run(
        app="app.asgi:app",
        host=C3_LISTEN_HOST,
        port=config.listen_port,
        reload=config.reload_debug,
        log_level="warning",
    )
