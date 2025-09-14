"""
Logging configuration and utilities.
"""

import os
import sys
import json
import logging
import logging.config
from datetime import datetime
from typing import Dict, Any, Optional

from app.utils.settings import settings


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields from the record
        for key, value in record.__dict__.items():
            if key not in ("name", "msg", "args", "levelname", "levelno", "pathname",
                          "filename", "module", "exc_info", "exc_text", "stack_info",
                          "lineno", "funcName", "created", "msecs", "relativeCreated",
                          "thread", "threadName", "processName", "process", "getMessage"):
                log_entry[key] = value
        
        # Mask PII if enabled
        if settings.mask_pii:
            log_entry = self._mask_pii(log_entry)
        
        return json.dumps(log_entry, ensure_ascii=False)
    
    def _mask_pii(self, log_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Mask potential PII in log entries."""
        sensitive_fields = {
            "password", "secret", "key", "token", "authorization", "auth",
            "ssn", "social_security", "credit_card", "card_number", "email",
            "phone", "address", "zip", "postal_code"
        }
        
        def mask_value(key: str, value: Any) -> Any:
            if isinstance(value, str) and any(field in key.lower() for field in sensitive_fields):
                if len(value) <= 4:
                    return "*" * len(value)
                return value[:2] + "*" * (len(value) - 4) + value[-2:]
            elif isinstance(value, dict):
                return {k: mask_value(k, v) for k, v in value.items()}
            elif isinstance(value, list):
                return [mask_value(str(i), item) for i, item in enumerate(value)]
            return value
        
        return {k: mask_value(k, v) for k, v in log_entry.items()}


def setup_logging() -> None:
    """Setup application logging configuration."""
    
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    
    # Create logs directory
    os.makedirs("logs", exist_ok=True)
    
    # Configure logging
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "json": {
                "()": JSONFormatter,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "json" if settings.is_production else "standard",
                "stream": sys.stdout,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": log_level,
                "formatter": "json",
                "filename": "logs/app.log",
                "maxBytes": 10 * 1024 * 1024,  # 10MB
                "backupCount": 5,
                "encoding": "utf-8",
            },
            "error_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": logging.ERROR,
                "formatter": "json",
                "filename": "logs/error.log",
                "maxBytes": 10 * 1024 * 1024,  # 10MB
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "app": {
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "uvicorn": {
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "celery": {
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
        },
        "root": {
            "level": log_level,
            "handlers": ["console", "file", "error_file"],
        },
    }
    
    logging.config.dictConfig(logging_config)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name."""
    return logging.getLogger(name)


def log_document_event(
    document_id: str,
    event_type: str,
    action: str,
    success: bool = True,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Log document processing events."""
    logger = get_logger("app.documents")
    
    log_data = {
        "document_id": document_id,
        "event_type": event_type,
        "action": action,
        "success": success,
    }
    
    if error:
        log_data["error"] = error
    
    if metadata:
        log_data["metadata"] = metadata
    
    if success:
        logger.info(f"Document {action}", extra=log_data)
    else:
        logger.error(f"Document {action} failed", extra=log_data)


def log_job_event(
    job_id: str,
    document_id: str,
    event_type: str,
    action: str,
    success: bool = True,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Log job processing events."""
    logger = get_logger("app.jobs")
    
    log_data = {
        "job_id": job_id,
        "document_id": document_id,
        "event_type": event_type,
        "action": action,
        "success": success,
    }
    
    if error:
        log_data["error"] = error
    
    if metadata:
        log_data["metadata"] = metadata
    
    if success:
        logger.info(f"Job {action}", extra=log_data)
    else:
        logger.error(f"Job {action} failed", extra=log_data)