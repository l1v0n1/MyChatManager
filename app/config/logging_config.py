import sys
import os
import logging
from loguru import logger
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from app.config.settings import settings


class LogConfig(BaseModel):
    """Logging configuration to be set for the server"""
    LOGGER_NAME: str = "chat_manager"
    LOG_FORMAT: str = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    LOG_LEVEL: str = "DEBUG" if settings.app.debug else "INFO"
    LOG_FILE_PATH: Optional[str] = os.getenv("LOG_FILE_PATH", "./logs/chat_manager.log")
    LOG_ROTATION: str = "10 MB"
    LOG_RETENTION: str = "1 month"


log_config = LogConfig()


class InterceptHandler(logging.Handler):
    """
    Default handler from examples in loguru documentation.
    See: https://loguru.readthedocs.io/en/stable/overview.html#entirely-compatible-with-standard-logging
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging() -> None:
    """
    Configure logging with loguru.
    """
    # Create logs directory if it doesn't exist
    if log_config.LOG_FILE_PATH:
        log_dir = os.path.dirname(log_config.LOG_FILE_PATH)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

    # Remove default handlers
    logger.remove()
    
    # Add console handler
    logger.add(
        sys.stderr,
        format=log_config.LOG_FORMAT,
        level=log_config.LOG_LEVEL,
        colorize=True,
    )
    
    # Add file handler if LOG_FILE_PATH is set
    if log_config.LOG_FILE_PATH:
        logger.add(
            log_config.LOG_FILE_PATH,
            format=log_config.LOG_FORMAT,
            level=log_config.LOG_LEVEL,
            rotation=log_config.LOG_ROTATION,
            retention=log_config.LOG_RETENTION,
        )

    # Intercept everything at the root logger
    logging.root.handlers = [InterceptHandler()]
    logging.root.setLevel(log_config.LOG_LEVEL)

    # Remove every other logger's handlers and propagate to root logger
    for name in logging.root.manager.loggerDict.keys():
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True

    # Configure standard library loggers
    logger.configure(handlers=[{"sink": sys.stderr, "level": log_config.LOG_LEVEL}])
    
    logger.info(f"Logging is configured. Level: {log_config.LOG_LEVEL}")
