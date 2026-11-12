from models.entity import Entity
from repositories.entity_repository import EntityRepository


def _entity_id():
    entity = EntityRepository().save_entity(
        Entity(name="Mira", entity_type="player_character"),
        campaign_id=1,
    )
    return entity.id


def _effect_payload(**overrides):
    payload = {
        "effect_type": "condition",
        "effect_key": "poisoned",
        "name": "Veneno de araña",
        "description": "Debilidad temporal.",
        "source_type": "creature",
        "duration_type": "conditional",
        "duration_condition": "Hasta recibir un antídoto",
    }
    payload.update(overrides)
    return payload


def test_persistent_effect_api_covers_create_list_status_and_removal(client):
    entity_id = _entity_id()
    created = client.post(
        f"/entities/{entity_id}/effects",
        json=_effect_payload(),
    )

    assert created.status_code == 201
    payload = created.json()
    assert payload["entity_id"] == entity_id
    assert payload["effect_type"] == "condition"
    assert payload["effect_key"] == "poisoned"
    assert payload["source_type"] == "creature"
    assert payload["duration_type"] == "conditional"
    assert payload["status"] == "active"
    assert payload["removed_at"] is None

    listed = client.get(f"/entities/{entity_id}/effects")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [payload["id"]]

    suspended = client.patch(
        f"/effects/{payload['id']}/status",
        json={"status": "suspended"},
    )
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "suspended"

    removed = client.delete(f"/effects/{payload['id']}")
    assert removed.status_code == 200
    assert removed.json()["status"] == "removed"
    assert removed.json()["removed_at"] is not None
    assert client.get(f"/entities/{entity_id}/effects").json() == []
    history = client.get(
        f"/entities/{entity_id}/effects", params={"include_removed": "true"}
    )
    assert history.status_code == 200
    assert [item["status"] for item in history.json()] == ["removed"]


def test_persistent_effect_api_maps_list_lookup_error_to_404(
    client, monkeypatch
):
    import app

    runtime = app.runtime_factory.get_runtime(1)

    def fail(*args, **kwargs):
        raise LookupError("entity not found")

    monkeypatch.setattr(runtime.persistent_effect_service, "list_for_entity", fail)
    response = client.get("/entities/999/effects")

    assert response.status_code == 404
    assert response.json()["detail"] == "entity not found"


def test_persistent_effect_api_maps_create_lookup_error_to_404(
    client, monkeypatch
):
    import app

    runtime = app.runtime_factory.get_runtime(1)

    def fail(**kwargs):
        raise LookupError("target entity not found")

    monkeypatch.setattr(runtime.persistent_effect_service, "create", fail)
    response = client.post("/entities/999/effects", json=_effect_payload())

    assert response.status_code == 404
    assert response.json()["detail"] == "target entity not found"


def test_persistent_effect_api_maps_create_value_error_to_422(
    client, monkeypatch
):
    import app

    runtime = app.runtime_factory.get_runtime(1)

    def fail(**kwargs):
        raise ValueError("effect shape rejected")

    monkeypatch.setattr(runtime.persistent_effect_service, "create", fail)
    response = client.post("/entities/999/effects", json=_effect_payload())

    assert response.status_code == 422
    assert response.json()["detail"] == "effect shape rejected"


def test_persistent_effect_api_maps_status_errors(client, monkeypatch):
    import app

    runtime = app.runtime_factory.get_runtime(1)

    def not_found(*args, **kwargs):
        raise LookupError("effect not found")

    monkeypatch.setattr(runtime.persistent_effect_service, "set_status", not_found)
    missing = client.patch(
        "/effects/missing/status", json={"status": "suspended"}
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "effect not found"

    def conflict(*args, **kwargs):
        raise ValueError("removed effects are terminal")

    monkeypatch.setattr(runtime.persistent_effect_service, "set_status", conflict)
    response = client.patch(
        "/effects/removed/status", json={"status": "active"}
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "removed effects are terminal"


def test_persistent_effect_api_maps_remove_lookup_error_to_404(
    client, monkeypatch
):
    import app

    runtime = app.runtime_factory.get_runtime(1)

    def fail(*args, **kwargs):
        raise LookupError("effect not found")

    monkeypatch.setattr(runtime.persistent_effect_service, "remove", fail)
    response = client.delete("/effects/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "effect not found"
