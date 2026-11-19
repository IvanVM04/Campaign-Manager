from dataclasses import dataclass

from services.discourse.contracts import (
    DiscourseSelection,
    SpeechPredicateSignal,
    SurfacePronounMention,
)
from services.discourse.renderer import DiscourseContextRenderer
from services.discourse.speaker_signal_extractor import SpeakerSignalExtractor
from services.discourse.surface_mention_extractor import SurfaceMentionExtractor
from services.discourse.topic_history_selector import DiscourseTopicHistorySelector
from services.discourse_context import DiscourseContextBuilder


@dataclass(frozen=True)
class Turn:
    id: int
    player_input: str
    narrative: str = ""


def test_topic_selector_exposes_typed_selection_and_preserves_facade_contract():
    selector = DiscourseTopicHistorySelector()
    history = (
        Turn(1, "Hablo con Mara junto al molino."),
        Turn(2, "Cambiando de tema, compro una espada."),
        Turn(3, "Revisamos el puente."),
    )

    selected = selector.select_history(history, "Retomando el molino, ¿qué vimos?")
    assert isinstance(selected, DiscourseSelection)
    assert selected.reason == "callback_anchor_match"
    assert selected.turns == (history[0],)
    assert selected.anchor_tokens == ("molino",)
    assert DiscourseContextBuilder.select_history(history, "Retomando el molino, ¿qué vimos?") == selected


def test_topic_selector_keeps_unanchored_callbacks_ambiguous():
    selector = DiscourseTopicHistorySelector()
    history = (
        Turn(1, "Miro el molino."),
        Turn(2, "Cambio de tema, entro en la torre."),
    )

    selected = selector.select_history(
        history,
        "Volviendo a lo anterior, ¿qué pasó?",
    )
    assert selected.reason == "callback_without_anchor"
    assert selected.ambiguous is True
    assert selected.turns == history


def test_topic_selector_reports_unmatched_callback_anchor_without_guessing():
    selector = DiscourseTopicHistorySelector()
    history = (
        Turn(1, "Miro el molino."),
        Turn(2, "Cambio de tema, entro en la torre."),
    )

    selected = selector.select_history(history, "Volviendo al dragón, ¿qué ocurrió?")
    assert selected.reason == "callback_anchor_unmatched"
    assert selected.ambiguous is True
    assert selected.turns == history


def test_topic_selector_recognizes_contracted_spanish_callback_markers():
    selector = DiscourseTopicHistorySelector()
    history = (
        Turn(1, "Miro el molino."),
        Turn(2, "Cambio de tema, entro en la torre."),
    )

    for utterance, anchor in (
        ("Regresando al molino, ¿qué vimos?", ("molino",)),
        ("Volvamos al faro, ¿qué ocurrió?", ("faro",)),
    ):
        selected = selector.select_history(history, utterance)
        assert selected.reason == "callback_anchor_unmatched"
        assert selected.anchor_tokens == anchor
        assert selected.ambiguous is True
        assert selected.turns == history


def test_surface_extractor_returns_literal_offsets_without_resolving_identity():
    extractor = SurfaceMentionExtractor()
    source = 'Ellas contestan; le pregunto por el mapa y Mara repite: «ella responde».'
    mentions = extractor.surface_pronoun_mentions(source)

    assert all(isinstance(item, SurfacePronounMention) for item in mentions)
    assert [item.text for item in mentions] == ["Ellas", "le"]
    assert [source[item.start:item.end] for item in mentions] == ["Ellas", "le"]
    assert all(not hasattr(item, "entity_id") for item in mentions)
    assert DiscourseContextBuilder.surface_pronoun_mentions(source) == mentions


def test_surface_extractor_uses_only_explicit_local_grammatical_markers():
    extractor = SurfaceMentionExtractor()
    assert extractor.grammatical_features("La capitana Mara entra.", "Mara") == (
        "feminine",
        "singular",
    )
    assert extractor.grammatical_features("Mara entra.", "Mara") == (None, None)
    assert extractor.pronoun_agreement("les") == ("unknown", "plural")


def test_speaker_extractor_requires_unique_visible_active_npc_alias():
    @dataclass
    class Entity:
        id: int
        name: str
        entity_type: str = "npc"
        active: bool = True
        aliases: tuple[str, ...] = ()

    extractor = SpeakerSignalExtractor()
    mara = Entity(1, "Mara", aliases=("La capitana",))
    signal = extractor.speech_predicate_signals(
        "Mara responde con calma.",
        visible_entities=(mara,),
    )
    assert signal == (
        SpeechPredicateSignal(
            subject="Mara",
            predicate="responde",
            subject_start=0,
            subject_end=4,
            predicate_start=5,
            predicate_end=13,
            gender="unknown",
            number="unknown",
            subject_kind="visible_npc",
        ),
    )
    ambiguous = extractor.speech_predicate_signals(
        "Mara responde.",
        visible_entities=(mara, Entity(2, "Mara")),
    )
    assert ambiguous == ()


def test_speaker_extractor_keeps_quotes_out_of_speech_signals():
    extractor = SpeakerSignalExtractor()
    assert extractor.speech_predicate_signals(
        'Mara repite: «Ellas contestan» y se marcha.'
    ) == ()


def test_renderer_composes_collaborators_and_keeps_history_out_of_current_evidence():
    renderer = DiscourseContextRenderer(
        DiscourseTopicHistorySelector(),
        SurfaceMentionExtractor(),
        SpeakerSignalExtractor(),
    )
    history = (Turn(4, "Hablo con Mara junto al molino."),)
    rendered = renderer.render("Retomando el molino, hazlo otra vez.", history)

    assert "Selección discursiva tipada: callback_anchor_match" in rendered
    assert "solo contexto, no evidencia" in rendered
    assert "historial, no evidencia actual" in rendered
    assert len(rendered.encode("utf-8")) <= renderer.MAX_RENDERED_CHARS


def test_renderer_and_facade_share_the_same_rendered_contract():
    history = (
        Turn(4, "Hablo con Mara.", "Mara dice: «Volveré pronto»."),
        Turn(5, "Cambiando de tema, compro una poción.", ""),
    )
    renderer = DiscourseContextRenderer(
        DiscourseTopicHistorySelector(),
        SurfaceMentionExtractor(),
        SpeakerSignalExtractor(),
    )
    rendered = renderer.render("Retomando a Mara, ¿qué dijo?", history)
    facade = DiscourseContextBuilder.render("Retomando a Mara, ¿qué dijo?", history)
    assert rendered == facade
