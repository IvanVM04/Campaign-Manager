def test_world_entity_read_api_filters_and_paginates(client):
    created = client.post(
        "/world/entities/bootstrap",
        json={
            "entities": [
                {
                    "name": "Aldric",
                    "entity_type": "character",
                    "description": "A travelling fighter.",
                },
                {
                    "name": "Aldora",
                    "entity_type": "character",
                    "description": "A village healer.",
                },
                {
                    "name": "Goblin",
                    "entity_type": "creature",
                    "description": "A small green raider.",
                },
            ],
        },
    )
    assert created.status_code == 200, created.text

    response = client.get(
        "/world/entities?q=ald&entity_type=character&limit=1"
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 2
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Aldric"
    assert data["items"][0]["entity_type"] == "character"

    next_page = client.get(
        "/world/entities?q=ald&entity_type=character&limit=1&offset=1"
    )
    assert next_page.status_code == 200
    assert [item["name"] for item in next_page.json()["items"]] == [
        "Aldora"
    ]


def test_world_entity_read_api_rejects_invalid_pagination(client):
    assert client.get("/world/entities?limit=0").status_code == 422
    assert client.get("/world/entities?limit=101").status_code == 422
    assert client.get("/world/entities?offset=-1").status_code == 422


def test_world_collection_read_endpoints_return_paginated_pages(client):
    for path in (
        "/world/items",
        "/world/item-instances",
        "/world/resources",
        "/world/resource-balances",
        "/world/relations",
        "/world/events",
    ):
        response = client.get(path)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["limit"] == 50
        assert data["offset"] == 0


def test_world_collection_read_endpoints_validate_pagination(client):
    assert client.get("/world/items?limit=0").status_code == 422
    assert client.get("/world/events?limit=101").status_code == 422
    assert client.get("/world/resources?offset=-1").status_code == 422
