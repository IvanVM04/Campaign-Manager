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
