import pytest


def test_dice_roll_returns_individual_results_and_total(client, monkeypatch):
    from rules_engine.dnd5e_2014.core.dice import DiceRoll

    class FakeDiceRoller:
        def roll(self, count, sides, *, modifier=0):
            assert (count, sides, modifier) == (3, 6, 2)
            return DiceRoll(3, 6, (2, 4, 6), 2, 14)

    monkeypatch.setattr(
        "api.routers.dice.DiceRoller",
        FakeDiceRoller,
    )

    response = client.post(
        "/dice/roll",
        json={"count": 3, "sides": 6, "modifier": 2},
    )

    assert response.status_code == 200
    assert response.json() == {
        "count": 3,
        "sides": 6,
        "rolls": [2, 4, 6],
        "selected": None,
        "roll_mode": "normal",
        "modifier": 2,
        "total": 14,
    }


@pytest.mark.parametrize(
    ("payload", "rolls", "selected", "mode", "total"),
    [
        ({"count": 1, "sides": 20}, (7,), 7, "normal", 7),
        ({"count": 1, "sides": 20, "advantage": True}, (7, 18), 18, "advantage", 18),
        ({"count": 1, "sides": 20, "disadvantage": True}, (7, 3), 3, "disadvantage", 3),
    ],
)
def test_d20_roll_supports_normal_advantage_and_disadvantage(
    client,
    monkeypatch,
    payload,
    rolls,
    selected,
    mode,
    total,
):
    from rules_engine.dnd5e_2014.core.dice import D20Roll, RollMode

    class FakeDiceRoller:
        def roll_d20(
            self,
            *,
            modifier=0,
            advantage=False,
            disadvantage=False,
        ):
            assert advantage is payload.get("advantage", False)
            assert disadvantage is payload.get("disadvantage", False)
            return D20Roll(
                rolls=rolls,
                selected=selected,
                mode=RollMode(mode),
                modifier=0,
                total=total,
            )

    monkeypatch.setattr(
        "api.routers.dice.DiceRoller",
        FakeDiceRoller,
    )

    response = client.post("/dice/roll", json=payload)

    assert response.status_code == 200
    assert response.json()["rolls"] == list(rolls)
    assert response.json()["selected"] == selected
    assert response.json()["roll_mode"] == mode
    assert response.json()["total"] == total


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"count": 0, "sides": 6},
        {"count": 101, "sides": 6},
        {"count": 1, "sides": 1},
        {"count": 1, "sides": 1001},
        {"count": 2, "sides": 20, "advantage": True},
        {"count": 1, "sides": 6, "disadvantage": True},
    ],
)
def test_dice_roll_rejects_invalid_input(client, payload):
    response = client.post("/dice/roll", json=payload)

    assert response.status_code == 422


def test_dice_roll_requires_campaign_header():
    from fastapi.testclient import TestClient

    from app import app

    response = TestClient(app).post(
        "/dice/roll",
        json={"count": 1, "sides": 20},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "bad_request"
