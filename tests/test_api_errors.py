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

    @app.get("/http-internal-error")
    def http_internal_error():
        raise HTTPException(status_code=500, detail="private database path")

    @app.get("/http-bad-gateway")
    def http_bad_gateway():
        raise HTTPException(status_code=502, detail="provider token leaked")

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
    from services.providers import LLMProviderError
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
    from services.llm_world import LLMExtractionError
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



def test_http_server_errors_do_not_expose_internal_details(error_client):
    internal = error_client.get("/http-internal-error")
    upstream = error_client.get("/http-bad-gateway")

    assert internal.status_code == 500
    assert internal.json() == {
        "detail": "Internal server error",
        "code": "internal_error",
    }
    assert upstream.status_code == 502
    assert upstream.json() == {
        "detail": "Bad gateway",
        "code": "upstream_invalid_response",
    }
    assert "private database path" not in internal.text
    assert "provider token leaked" not in upstream.text



@pytest.mark.parametrize(
    ("code", "status_code"),
    [
        ("stale_context", 409),
        ("operation_validation_failed", 409),
        ("turn_execution_failed", 500),
    ],
)
def test_durable_turn_error_uses_stable_typed_code(code, status_code):
    from api.errors import api_error_for_exception
    from services.turns.durable_native_turn_service import DurableNativeTurnError

    error = DurableNativeTurnError("trusted internal message", code=code)
    mapped = api_error_for_exception(
        error,
        fallback_status=409,
        fallback_code="conflict",
        fallback_detail=str(error),
    )

    assert mapped.status_code == status_code
    assert mapped.code == code


def test_forbidden_model_character_operation_maps_to_invalid_model_response():
    from api.errors import api_error_for_exception
    from services.turns.turn_resolution_service import TurnResolutionServiceError

    error = TurnResolutionServiceError(
        "character-state changes must come from deterministic mechanics",
        code="character_operation_not_allowed",
    )
    mapped = api_error_for_exception(error, fallback_status=409)

    assert mapped.status_code == 502
    assert mapped.code == "invalid_llm_response"


def test_wrapped_invalid_intent_interpretation_maps_to_bad_gateway():
    from api.errors import api_error_for_exception
    from services.turns.durable_native_turn_service import DurableNativeTurnError
    from services.turns.intent_interpreter import IntentInterpreterError
    from services.turns.turn_resolution_service import TurnResolutionServiceError

    try:
        try:
            raise IntentInterpreterError("invalid semantic schema")
        except IntentInterpreterError as intent_error:
            raise TurnResolutionServiceError("intent interpretation failed") from intent_error
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
