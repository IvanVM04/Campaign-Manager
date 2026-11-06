import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.errors import APIError, register_error_handlers


@pytest.fixture
def error_client():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/http-error")
    def http_error():
        raise HTTPException(status_code=404, detail="resource not found")

    @app.get("/application-error")
    def application_error():
        raise APIError(
            status_code=409,
            code="stale_state",
            detail="The supplied version is stale.",
        )

    @app.get("/unexpected-error")
    def unexpected_error():
        raise RuntimeError("private database path")

    @app.get("/application-internal-error")
    def application_internal_error():
        raise APIError(
            status_code=500,
            code="database_failure",
            detail="private database path",
        )

    @app.post("/validation-error")
    def validation_error(quantity: int):
        return {"quantity": quantity}

    return TestClient(app, raise_server_exceptions=False)


def test_http_exception_keeps_detail_and_adds_stable_code(error_client):
    response = error_client.get("/http-error")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "resource not found",
        "code": "not_found",
    }


def test_application_error_exposes_domain_code(error_client):
    response = error_client.get("/application-error")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "The supplied version is stale.",
        "code": "stale_state",
    }


def test_validation_error_does_not_echo_submitted_input(error_client):
    response = error_client.post(
        "/validation-error?quantity=private-value"
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.json()["detail"][0]["loc"] == ["query", "quantity"]
    assert "input" not in response.json()["detail"][0]
    assert "private-value" not in response.text


def test_unexpected_error_is_logged_but_not_exposed(error_client):
    response = error_client.get("/unexpected-error")

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Internal server error",
        "code": "internal_error",
    }
    assert "private database path" not in response.text


def test_application_server_error_does_not_expose_internal_detail(error_client):
    response = error_client.get("/application-internal-error")

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Internal server error",
        "code": "database_failure",
    }
    assert "private database path" not in response.text



def test_wrapped_llm_provider_failure_maps_to_service_unavailable():
    from api.errors import api_error_for_exception
    from services.llm_provider import LLMProviderError
    from services.turns.durable_native_turn_service import DurableNativeTurnError
    from services.turns.turn_resolution_service import TurnResolutionServiceError

    try:
        try:
            raise LLMProviderError("connection refused")
        except LLMProviderError as provider_error:
            raise TurnResolutionServiceError("extractor failed") from provider_error
    except TurnResolutionServiceError as resolver_error:
        wrapped = DurableNativeTurnError("native turn execution failed")
        wrapped.__cause__ = resolver_error

    error = api_error_for_exception(
        wrapped,
        fallback_status=409,
        fallback_code="turn_conflict",
    )

    assert error.status_code == 503
    assert error.code == "llm_provider_unavailable"


def test_wrapped_invalid_llm_response_maps_to_bad_gateway():
    from api.errors import api_error_for_exception
    from services.llm_world_extractor import LLMExtractionError
    from services.turns.durable_native_turn_service import DurableNativeTurnError
    from services.turns.turn_resolution_service import TurnResolutionServiceError

    try:
        try:
            raise LLMExtractionError("unknown operation type")
        except LLMExtractionError as extraction_error:
            raise TurnResolutionServiceError("extractor failed") from extraction_error
    except TurnResolutionServiceError as resolver_error:
        wrapped = DurableNativeTurnError("native turn execution failed")
        wrapped.__cause__ = resolver_error

    error = api_error_for_exception(
        wrapped,
        fallback_status=409,
        fallback_code="turn_conflict",
    )

    assert error.status_code == 502
    assert error.code == "invalid_llm_response"
