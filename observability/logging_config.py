"""Centralized console and rotating JSON-lines logging configuration."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from observability.log_context import (
    current_campaign_id,
    current_request_id,
    current_resolution_id,
)

_DEFAULT_LOG_FILE = Path("logs/campaign-manager.jsonl")
_SENSITIVE_VALUE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|password|authorization)\b"
    r"(\s*[:=]\s*)(['\"]?)[^\s,'\";}]+"
)
_BEARER_VALUE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*")
_SAFE_EXTRA_FIELDS = (
    "http_method",
    "http_path",
    "status_code",
    "duration_ms",
    "provider_role",
    "provider_model",
    "response_chars",
    "prompt_chars",
    "prompt_estimated_tokens",
    "prompt_budget_tokens",
    "prompt_budget_utilization",
    "context_estimated_tokens",
    "context_budget_tokens",
    "available_records",
    "candidate_records",
    "selected_records",
    "excluded_records",
    "selected_counts",
    "adapter_namespace",
    "lifecycle_state",
    "dice_mode",
    "error_code",
    "error_type",
)


def _redact(value: str) -> str:
    value = _BEARER_VALUE.sub("Bearer [REDACTED]", value)
    return _SENSITIVE_VALUE.sub(r"\1\2[REDACTED]", value)


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    level: int = logging.INFO
    console_format: str = "text"
    log_file: Path | None = _DEFAULT_LOG_FILE
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> LoggingSettings:
        values = os.environ if environ is None else environ
        levels = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        level_name = values.get("CAMPAIGN_MANAGER_LOG_LEVEL", "INFO").strip().upper()
        if level_name not in levels:
            raise ValueError(
                "CAMPAIGN_MANAGER_LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR or CRITICAL"
            )
        level_value = levels[level_name]

        console_format = values.get(
            "CAMPAIGN_MANAGER_LOG_CONSOLE_FORMAT", "text"
        ).strip().lower()
        if console_format not in {"text", "json"}:
            raise ValueError("CAMPAIGN_MANAGER_LOG_CONSOLE_FORMAT must be text or json")

        raw_path = values.get(
            "CAMPAIGN_MANAGER_LOG_FILE",
            str(_DEFAULT_LOG_FILE),
        ).strip()
        log_file = (
            None
            if raw_path.casefold() in {"", "off", "none", "disabled"}
            else Path(raw_path).expanduser()
        )

        try:
            max_bytes = int(
                values.get("CAMPAIGN_MANAGER_LOG_MAX_BYTES", str(10 * 1024 * 1024))
            )
            backup_count = int(values.get("CAMPAIGN_MANAGER_LOG_BACKUP_COUNT", "5"))
        except ValueError as exc:
            raise ValueError("log rotation settings must be integers") from exc
        if max_bytes <= 0:
            raise ValueError("CAMPAIGN_MANAGER_LOG_MAX_BYTES must be greater than zero")
        if backup_count < 0 or backup_count > 100:
            raise ValueError("CAMPAIGN_MANAGER_LOG_BACKUP_COUNT must be between 0 and 100")

        return cls(
            level=level_value,
            console_format=console_format,
            log_file=log_file,
            max_bytes=max_bytes,
            backup_count=backup_count,
        )


class LogContextFilter(logging.Filter):
    """Attach correlation identifiers without requiring each caller to pass them."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", None):
            record.request_id = current_request_id() or "-"
        if not getattr(record, "campaign_id", None):
            record.campaign_id = current_campaign_id() or "-"
        if not getattr(record, "resolution_id", None):
            record.resolution_id = current_resolution_id() or "-"
        return True


class JsonLineFormatter(logging.Formatter):
    """Serialize an allowlisted set of diagnostic fields as one JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(
            record.created,
            tz=UTC,
        ).isoformat(timespec="milliseconds")
        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": _redact(record.getMessage()),
        }
        for field_name in ("request_id", "campaign_id", "resolution_id", *_SAFE_EXTRA_FIELDS):
            value = getattr(record, field_name, None)
            if value is not None and value != "-":
                payload[field_name] = _redact(value) if isinstance(value, str) else value
        if record.exc_info:
            payload["exception"] = _redact(self.formatException(record.exc_info))
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )


_MANAGED_HANDLERS: list[logging.Handler] = []
_CONFIGURE_LOCK = threading.RLock()


def configure_logging(
    settings: LoggingSettings | None = None,
) -> LoggingSettings:
    """Configure root logging once, or replace only this package's handlers."""
    resolved = settings or LoggingSettings.from_env()
    with _CONFIGURE_LOCK:
        root = logging.getLogger()
        for handler in tuple(_MANAGED_HANDLERS):
            root.removeHandler(handler)
            handler.close()
        _MANAGED_HANDLERS.clear()

        context_filter = LogContextFilter()
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(resolved.level)
        console_handler.addFilter(context_filter)
        if resolved.console_format == "json":
            console_handler.setFormatter(JsonLineFormatter())
        else:
            console_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)s "
                    "request_id=%(request_id)s campaign_id=%(campaign_id)s "
                    "resolution_id=%(resolution_id)s %(name)s: %(message)s"
                )
            )
        root.addHandler(console_handler)
        _MANAGED_HANDLERS.append(console_handler)

        if resolved.log_file is not None:
            resolved.log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                resolved.log_file,
                maxBytes=resolved.max_bytes,
                backupCount=resolved.backup_count,
                encoding="utf-8",
                delay=True,
            )
            file_handler.setLevel(resolved.level)
            file_handler.addFilter(context_filter)
            file_handler.setFormatter(JsonLineFormatter())
            root.addHandler(file_handler)
            _MANAGED_HANDLERS.append(file_handler)

        root.setLevel(resolved.level)
        logging.captureWarnings(True)
    return resolved
