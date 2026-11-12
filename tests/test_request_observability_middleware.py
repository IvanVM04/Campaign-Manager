from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.errors import register_error_handlers
from observability.log_context import (
    current_campaign_id,
    current_request_id,
)
from observability.middleware import RequestObservabilityMiddleware


def create_observability_client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(RequestObservabilityMiddleware)

    @app.get("/correlation")
    def correlation():
        return {
            "request_id": current_request_id(),
            "campaign_id": current_campaign_id(),
        }

    @app.get("/failure")
    def failure():
        raise RuntimeError("private storage location")

    @app.get("/validation")
    def validation(value: int):
        return {"value": value}

    return TestClient(app, raise_server_exceptions=False)


def test_request_id_and_campaign_context_are_visible_and_echoed():
    client = create_observability_client()

    response = client.get(
        "/correlation",
        headers={
            "X-Request-ID": "desktop-ui-request-42",
            "X-Campaign-Id": "7",
        },
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "desktop-ui-request-42"
    assert response.json() == {
        "request_id": "desktop-ui-request-42",
        "campaign_id": "7",
    }
    assert current_request_id() is None
    assert current_campaign_id() is None


def test_invalid_request_id_is_replaced_with_a_safe_generated_identifier():
    response = create_observability_client().get(
        "/correlation",
        headers={"X-Request-ID": "invalid/request/id"},
    )

    request_id = response.headers["X-Request-ID"]
    assert response.status_code == 200
    assert len(request_id) == 32
    assert all(character in "0123456789abcdef" for character in request_id)
    assert response.json()["request_id"] == request_id


def test_unexpected_error_is_sanitized_but_keeps_request_correlation(caplog):
    client = create_observability_client()

    with caplog.at_level(logging.ERROR):
        response = client.get(
            "/failure",
            headers={
                "X-Request-ID": "failure-correlation-9",
                "X-Campaign-Id": "3",
            },
        )

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "failure-correlation-9"
    assert response.json() == {
        "detail": "Internal server error",
        "code": "internal_error",
    }
    assert "private storage location" not in response.text
    failure_records = [
        record
        for record in caplog.records
        if record.getMessage() == "Unhandled API exception"
    ]
    assert len(failure_records) == 1
    assert failure_records[0].request_id == "failure-correlation-9"
    assert failure_records[0].campaign_id == "3"


def test_validation_errors_also_echo_request_id():
    response = create_observability_client().get(
        "/validation?value=not-an-integer",
        headers={"X-Request-ID": "validation-request-5"},
    )

    assert response.status_code == 422
    assert response.headers["X-Request-ID"] == "validation-request-5"
    assert response.json()["code"] == "validation_error"
