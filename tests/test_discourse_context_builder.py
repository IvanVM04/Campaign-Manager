"""Deterministic discourse-signal tests for the advanced shared context."""

from types import SimpleNamespace

from models.entity import Entity
from services.discourse_context import DiscourseContextBuilder


def turn(turn_id: int, player_input: str = "", narrative: str = ""):
    return SimpleNamespace(
        id=turn_id,
        player_input=player_input,
        narrative=narrative,
    )


def test_topic_segments_split_only_on_explicit_topic_markers():
    history = [
        turn(1, "Hablo con Mara."),
        turn(2, "Ella me entrega la llave."),
        turn(3, "Cambiando de tema, inspecciono la torre."),
        turn(4, "La puerta está cerrada."),
    ]
    assert DiscourseContextBuilder.topic_segments(history) == (0, 0, 1, 1)


def test_topic_scope_uses_latest_segment_by_default():
    history = [
        turn(1, "Hablo con Mara."),
        turn(2, "Cambiando de tema, inspecciono la torre."),
        turn(3, "Busco una entrada."),
    ]
    scoped = DiscourseContextBuilder.scope_history(history, "Ella responde.")
    assert [item.id for item in scoped] == [2, 3]


def test_explicit_callback_can_reopen_bounded_previous_segments():
    history = [
        turn(1, "Hablo con Mara."),
        turn(2, "Cambiando de tema, inspecciono la torre."),
        turn(3, "Busco una entrada."),
    ]
    scoped = DiscourseContextBuilder.scope_history(
        history,
        "Volviendo a lo de Mara, ella responde.",
    )
    assert [item.id for item in scoped] == [1, 2, 3]


def test_current_topic_shift_does_not_inherit_previous_focus():
    history = [turn(1, "Hablo con Mara.")]
    assert DiscourseContextBuilder.scope_history(
        history,
        "Cambiando de tema, ¿qué hay en la torre?",
    ) == ()


def test_ellipsis_cues_are_rendered_as_hints_not_automatic_resolution():
    rendered = DiscourseContextBuilder.render(
        "Hazlo otra vez.",
        [turn(1, "Intento abrir la puerta.")],
    )
    assert "Posible elipsis" in rendered
    assert "antecedente único" in rendered


def test_grammatical_features_require_explicit_local_article_and_apposition():
    assert DiscourseContextBuilder.grammatical_features(
        "La guardia Mara entra en la sala.",
        "Mara",
    ) == ("feminine", "singular")
    assert DiscourseContextBuilder.grammatical_features(
        "El capitán Aldric espera.",
        "Aldric",
    ) == ("masculine", "singular")
    assert DiscourseContextBuilder.grammatical_features(
        "Mara entra en la sala.",
        "Mara",
    ) == (None, None)


def test_plural_agreement_is_not_collapsed_to_a_single_entity():
    assert DiscourseContextBuilder.pronoun_agreement("Ellos") == (
        "masculine",
        "plural",
    )
    assert DiscourseContextBuilder.pronoun_agreement("Ellas") == (
        "feminine",
        "plural",
    )


def test_explicitly_labelled_npc_quote_is_attributed_to_visible_active_speaker():
    mara = Entity(id=1, name="Mara", entity_type="npc")
    inactive = Entity(id=2, name="Bram", entity_type="npc", active=False)
    found = DiscourseContextBuilder.extract_npc_utterances(
        "Mara dice: «Aldric está en la torre». Bram responde: «No».",
        10,
        (mara, inactive),
    )
    assert len(found) == 1
    assert found[0].speaker_entity_id == 1
    assert found[0].speaker_name == "Mara"
    assert found[0].utterance == "Aldric está en la torre"


def test_ambiguous_speaker_alias_is_not_attributed():
    first = Entity(id=1, name="Mara", entity_type="npc")
    second = Entity(id=2, name="Mara", entity_type="npc")
    found = DiscourseContextBuilder.extract_npc_utterances(
        "Mara dice: «No lo sé».",
        11,
        (first, second),
    )
    assert found == ()


def test_narrative_without_explicit_speaker_label_is_not_npc_dialogue():
    mara = Entity(id=1, name="Mara", entity_type="npc")
    found = DiscourseContextBuilder.extract_npc_utterances(
        "Mara mira la puerta y parece preocupada.",
        12,
        (mara,),
    )
    assert found == ()



def test_quoted_topic_shift_marker_does_not_split_the_current_topic():
    history = [
        turn(30, "Hablo con Mara sobre el contrato."),
        turn(31, "Mara dice: «cambiando de tema» y señala la puerta."),
    ]

    assert DiscourseContextBuilder.has_topic_shift(
        "Mara susurra: «cambiando de tema» y después se ríe."
    ) is False
    assert DiscourseContextBuilder.topic_segments(history) == (0, 0)
    assert [
        item.id
        for item in DiscourseContextBuilder.scope_history(
            history,
            "¿Qué quiso decir con esa frase?",
        )
    ] == [30, 31]


def test_quoted_callback_marker_does_not_reopen_an_older_topic():
    history = [
        turn(40, "Hablo con Mara sobre el mapa."),
        turn(41, "Cambiando de tema, entro en la torre."),
        turn(42, "Busco una escalera."),
    ]

    current_input = "Mara repite: «volviendo a lo de antes» y se marcha."
    assert DiscourseContextBuilder.reactivates_prior_topic(current_input) is False
    assert [
        item.id
        for item in DiscourseContextBuilder.scope_history(history, current_input)
    ] == [41, 42]


def test_quoted_ellipsis_marker_is_not_rendered_as_a_current_action_cue():
    rendered = DiscourseContextBuilder.render(
        "Mara repite: «hazlo otra vez» y después se marcha.",
        [turn(50, "Intento abrir la puerta.")],
    )

    assert "Posible elipsis" not in rendered
