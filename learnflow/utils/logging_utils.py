"""
Utility functions for logging configuration across all services.
"""

import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional


def setup_logging(
    service_name: str,
    log_file: str,
    log_level: str = "INFO",
    log_dir: str = "logs",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 3,
    use_rotation: bool = True
) -> logging.Logger:
    """
    Configure logging with both console and file handlers.
    
    Args:
        service_name: Name of the service for logger
        log_file: Name of the log file
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directory for log files
        max_bytes: Maximum size of log file before rotation (default 10MB)
        backup_count: Number of backup files to keep (default 3)
        use_rotation: Whether to use rotating file handler (default True)
        
    Returns:
        Configured logger instance
    """
    # Create logs directory if it doesn't exist
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Create handlers
    handlers = [
        logging.StreamHandler(),  # Console output
    ]
    
    # Add file handler with optional rotation
    log_file_path = log_path / log_file
    if use_rotation:
        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
    else:
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
    
    handlers.append(file_handler)
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True  # Force reconfiguration if already configured
    )
    
    # Get logger for the service
    logger = logging.getLogger(service_name)
    logger.info(f"Logging initialized for {service_name} at level {log_level}")
    logger.info(f"Log file: {log_file_path}")
    
    return logger


def log_with_timing(logger: logging.Logger, start_time: float, end_time: float, operation: str, **kwargs):
    """
    Log operation with timing information.
    
    Args:
        logger: Logger instance
        start_time: Start time from time.time()
        end_time: End time from time.time()
        operation: Name of the operation
        **kwargs: Additional context to log
    """
    duration = end_time - start_time
    context_str = ", ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else ""
    
    if duration > 5.0:
        logger.warning(f"{operation} took {duration:.2f}s (slow){', ' + context_str if context_str else ''}")
    else:
        logger.info(f"{operation} completed in {duration:.2f}s{', ' + context_str if context_str else ''}")


class LogContext:
    """Context manager for timing operations."""
    
    def __init__(self, logger: logging.Logger, operation: str, log_level: str = "INFO"):
        self.logger = logger
        self.operation = operation
        self.log_level = getattr(logging, log_level.upper())
        self.start_time: Optional[float] = None
    
    def __enter__(self):
        import time
        self.start_time = time.time()
        self.logger.log(self.log_level, f"Starting {self.operation}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        end_time = time.time()
        duration = end_time - self.start_time if self.start_time else 0
        
        if exc_type:
            self.logger.error(f"{self.operation} failed after {duration:.2f}s: {exc_val}")
        else:
            if duration > 5.0:
                self.logger.warning(f"{self.operation} completed in {duration:.2f}s (slow)")
            else:
                self.logger.log(self.log_level, f"{self.operation} completed in {duration:.2f}s")