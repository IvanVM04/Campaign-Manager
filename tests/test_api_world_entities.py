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
