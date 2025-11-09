"""Centralized logging configuration for production observability.

Provides consistent logging setup across the application with:
- Structured format
- Request ID tracking
- Environment-aware output
"""
import logging
import os
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Setup a logger with consistent formatting.
    
    Args:
        name: Logger name (typically module name)
        level: Logging level (default INFO)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # Determine log directory based on environment
    is_railway = os.environ.get("RAILWAY_ENVIRONMENT") is not None
    log_dir = "/tmp/logs" if is_railway else "workspace/logs"
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # File handler with daily rotation
    log_file = os.path.join(log_dir, "app.log")
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        backupCount=7,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console handler for development and Railway logs
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get or create a logger with the given name.
    
    Args:
        name: Logger name (use __name__ from calling module)
    
    Returns:
        Configured logger instance
    """
    return setup_logger(name)
