import sys

from app.config import config
from app.utils.logging_utils import configure_terminal_logger


CENTINELA_API_BIND_HOST = "127.0.0.1"
# Fail closed for the Centinela profile even if a legacy config.toml still
# contains listen_host = "0.0.0.0".
config.listen_host = CENTINELA_API_BIND_HOST


def __init_logger():
    # _log_file = utils.storage_dir("logs/server.log")
    _lvl = config.log_level

    configure_terminal_logger(
        sys.stdout,
        level=_lvl,
        colorize=True,
    )

    # logger.add(
    #     _log_file,
    #     level=_lvl,
    #     format=format_log_record,
    #     rotation="00:00",
    #     retention="3 days",
    #     backtrace=True,
    #     diagnose=True,
    #     enqueue=True,
    # )


__init_logger()
