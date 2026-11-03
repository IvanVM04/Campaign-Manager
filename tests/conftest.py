import pytest
from fastapi.testclient import TestClient

from models.world_state import WorldState


@pytest.fixture
def empty_world():
    return WorldState(
        entities={},
        items={},
        item_instances={},
        resources={},
        resource_balances={},
        relations={},
    )


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    """
    Aísla cada test en una base SQLite temporal.
    """

    import database

    test_db_path = tmp_path / "campaign_test.db"

    monkeypatch.setattr(
        database,
        "DB_PATH",
        test_db_path,
    )

    database.init_db()

    import app
    from services.campaign_runtime import CampaignRuntimeFactory

    monkeypatch.setattr(
        app,
        "runtime_factory",
        CampaignRuntimeFactory(),
    )

    yield

@pytest.fixture
def client():
    import app

    return TestClient(
        app.app,
        headers={"X-Campaign-Id": "1"},
    )