from __future__ import annotations

import json
import logging

import pytest

from observability.log_context import bind_log_context
from observability.logging_config import (
    JsonLineFormatter,
    LogContextFilter,
    LoggingSettings,
)


def test_logging_settings_parse_levels_formats_and_disabled_file():
    settings = LoggingSettings.from_env(
        {
            "CAMPAIGN_MANAGER_LOG_LEVEL": "DEBUG",
            "CAMPAIGN_MANAGER_LOG_CONSOLE_FORMAT": "json",
            "CAMPAIGN_MANAGER_LOG_FILE": "off",
            "CAMPAIGN_MANAGER_LOG_MAX_BYTES": "2048",
            "CAMPAIGN_MANAGER_LOG_BACKUP_COUNT": "2",
        }
    )

    assert settings.level == logging.DEBUG
    assert settings.console_format == "json"
    assert settings.log_file is None
    assert settings.max_bytes == 2048
    assert settings.backup_count == 2


@pytest.mark.parametrize(
    "environ",
    [
        {"CAMPAIGN_MANAGER_LOG_LEVEL": "TRACE"},
        {"CAMPAIGN_MANAGER_LOG_CONSOLE_FORMAT": "xml"},
        {"CAMPAIGN_MANAGER_LOG_MAX_BYTES": "0"},
        {"CAMPAIGN_MANAGER_LOG_BACKUP_COUNT": "-1"},
        {"CAMPAIGN_MANAGER_LOG_BACKUP_COUNT": "101"},
    ],
)
def test_logging_settings_reject_invalid_configuration(environ):
    with pytest.raises(ValueError):
        LoggingSettings.from_env(environ)


def test_json_formatter_includes_correlation_and_allowlisted_fields_only():
    record = logging.LogRecord(
        name="tests.observability",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="provider call completed api_key=must-not-leak Bearer access-token",
        args=(),
        exc_info=None,
    )
    record.provider_role = "extraction"
    record.provider_model = "test-model"
    record.duration_ms = 123.4
    record.prompt = "full internal prompt must not be serialized"
    record.secret_value = "private campaign secret"

    with bind_log_context(
        request_id="request-123",
        campaign_id="7",
        resolution_id="91",
    ):
        LogContextFilter().filter(record)
        payload = json.loads(JsonLineFormatter().format(record))

    assert payload["request_id"] == "request-123"
    assert payload["campaign_id"] == "7"
    assert payload["resolution_id"] == "91"
    assert payload["provider_role"] == "extraction"
    assert payload["provider_model"] == "test-model"
    assert payload["duration_ms"] == 123.4
    assert "prompt" not in payload
    assert "secret_value" not in payload
    assert "must-not-leak" not in payload["message"]
    assert "access-token" not in payload["message"]


def test_log_context_is_restored_after_nested_bindings():
    from observability.log_context import (
        current_campaign_id,
        current_request_id,
        current_resolution_id,
    )

    with bind_log_context(request_id="outer", campaign_id="1"):
        assert current_request_id() == "outer"
        assert current_campaign_id() == "1"
        with bind_log_context(resolution_id="22", request_id="inner"):
            assert current_request_id() == "inner"
            assert current_resolution_id() == "22"
        assert current_request_id() == "outer"
        assert current_campaign_id() == "1"
        assert current_resolution_id() is None

    assert current_request_id() is None
    assert current_campaign_id() is None
