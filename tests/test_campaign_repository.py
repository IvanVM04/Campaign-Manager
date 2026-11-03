from repositories.campaign_repository import CampaignRepository


def test_get_campaign_returns_none_for_missing_campaign():
    repository = CampaignRepository()

    assert repository.get_campaign(999999) is None


def test_get_session_returns_none_for_missing_session():
    repository = CampaignRepository()

    assert repository.get_session(999999, campaign_id=1) is None


def test_get_current_session_returns_none_for_missing_campaign():
    repository = CampaignRepository()

    assert repository.get_current_session(999999) is None


def test_create_session_and_get_session():
    repository = CampaignRepository()

    session = repository.create_session(
        number=999,
        campaign_id=1,
        title="Test Session",
        summary="Resumen de prueba.",
        start_location="Vorder's Hold",
        end_location="La mina",
        notes="Notas de prueba.",
    )

    assert session is not None
    assert session["number"] == 999
    assert session["title"] == "Test Session"
    assert session["summary"] == "Resumen de prueba."
    assert session["start_location"] == "Vorder's Hold"
    assert session["end_location"] == "La mina"
    assert session["notes"] == "Notas de prueba."


def test_get_current_session_returns_none_when_campaign_has_no_session(
    isolated_database,
):
    repository = CampaignRepository()

    campaign = repository.get_campaign(1)

    assert campaign is not None
    assert campaign["current_session_id"] is None

    assert repository.get_current_session(1) is None

def test_fresh_database_creates_default_campaign():
    repository = CampaignRepository()

    campaign = repository.get_campaign(1)

    assert campaign is not None
    assert campaign["id"] == 1
    assert campaign["system"] == "D&D 5e 2014"

def test_mutating_methods_use_supplied_connection(
    isolated_database,
):
    from database import get_conn

    repository = CampaignRepository()

    campaign = repository.get_campaign(1)
    assert campaign is not None

    with get_conn() as conn:
        session = repository.create_session(
            number=1000,
            campaign_id=1,
            title="Transactional Session",
            summary="Resumen.",
            start_location="Vorder's Hold",
            end_location="La mina",
            notes="Notas.",
            conn=conn,
        )

        assert session is not None

        updated_campaign = repository.update_campaign(
            campaign["id"],
            name=campaign["name"],
            system=campaign["system"],
            tone=campaign["tone"],
            summary="Resumen actualizado.",
            conn=conn,
        )

        assert updated_campaign is not None
        assert updated_campaign["summary"] == (
            "Resumen actualizado."
        )

        updated_campaign = repository.update_current_session(
            campaign["id"],
            session["id"],
            conn=conn,
        )

        assert updated_campaign is not None
        assert updated_campaign["current_session_id"] == (
            session["id"]
        )