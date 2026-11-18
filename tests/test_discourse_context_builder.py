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
    assert [item.id for item in scoped] == [1]


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



def test_callback_without_a_lexical_anchor_preserves_history_for_abstention():
    history = [
        turn(1, "Hablo con Mara sobre el mapa."),
        turn(2, "Cambiando de tema, inspecciono la torre."),
        turn(3, "Busco una entrada."),
    ]

    scoped = DiscourseContextBuilder.scope_history(
        history,
        "Volviendo a lo anterior, ¿qué pasó?",
    )
    rendered = DiscourseContextBuilder.render(
        "Volviendo a lo anterior, ¿qué pasó?",
        history,
    )

    assert [item.id for item in scoped] == [1, 2, 3]
    assert "sin ancla que coincida" in rendered


def test_callback_anchor_selects_the_matching_older_topic_segment():
    history = [
        turn(1, "Hablo con Mara sobre el mapa."),
        turn(2, "Cambiando de tema, inspecciono la torre."),
        turn(3, "Busco una entrada lateral."),
    ]

    scoped = DiscourseContextBuilder.scope_history(
        history,
        "Volviendo a lo de Mara, le pregunto por el mapa.",
    )

    assert [item.id for item in scoped] == [1]


def test_ellipsis_hint_exposes_historical_candidate_not_new_evidence():
    rendered = DiscourseContextBuilder.render(
        "Hazlo otra vez, por favor.",
        [turn(1, "Intento abrir la puerta de roble.")],
    )

    assert "Posible elipsis" in rendered
    assert "turno 1" in rendered
    assert "Intento abrir la puerta de roble" in rendered
    assert "no evidencia actual" in rendered
    assert "no copies sus verbos" in rendered


def test_unique_explicit_grammatical_agreement_hints_npc_actor_without_renaming_pronoun():
    mara = Entity(id=1, name="Mara", entity_type="npc")
    aldric = Entity(id=2, name="Aldric", entity_type="npc")
    history = [
        turn(60, "La guardia Mara y el capitán Aldric esperan junto a la puerta.")
    ]

    rendered = DiscourseContextBuilder.render(
        "Ella responde en voz alta.",
        history,
        visible_entities=(mara, aldric),
    )

    assert "Concordancia explícita del sujeto" in rendered
    assert "Mara" in rendered
    assert "no lo sustituyas por el nombre" in rendered


def test_ambiguous_third_person_subject_does_not_default_to_player_actor():
    mara = Entity(id=1, name="Mara", entity_type="npc")
    aldric = Entity(id=2, name="Aldric", entity_type="npc")
    history = [
        turn(61, "Mara entra por el pasillo. Aldric espera junto a la mesa.")
    ]

    rendered = DiscourseContextBuilder.render(
        "Ella entra en la sala.",
        history,
        visible_entities=(mara, aldric),
    )

    normalized_rendered = " ".join(rendered.casefold().split())
    assert "está en tercera persona" in normalized_rendered
    assert "no lo conviertas automáticamente en una acción del jugador" in normalized_rendered


def test_plural_pronoun_remains_a_group_of_npcs_not_a_single_entity():
    mara = Entity(id=1, name="Mara", entity_type="npc")
    lia = Entity(id=2, name="Lía", entity_type="npc")
    history = [
        turn(62, "La guardia Mara y la mercadera Lía esperan junto al balcón.")
    ]

    rendered = DiscourseContextBuilder.render(
        "Ellas contestan en voz alta desde el balcón.",
        history,
        visible_entities=(mara, lia),
    )

    assert "sujeto plural" in rendered
    assert "grupo" in rendered
    assert "Mara" in rendered and "Lía" in rendered
    assert "no lo reduzcas a una persona" in rendered


def test_ambiguous_historical_npc_alias_is_flagged_without_speaker_attribution():
    first = Entity(id=1, name="Mara", entity_type="npc")
    second = Entity(id=2, name="Mara", entity_type="npc")
    history = [
        turn(63, "Dos personas hablan a la vez.", 'Mara dice: «No lo sé».')
    ]

    rendered = DiscourseContextBuilder.render(
        "No estoy seguro de quién lo dijo; ¿puedes identificar quién habló?",
        history,
        visible_entities=(first, second),
    )

    assert "Alias histórico de hablante ambiguo" in rendered
    assert "corresponde a varios NPC" in rendered
    assert "NPC Mara (turno 63)" not in rendered


def test_current_unquoted_speech_predicates_are_cued_but_quoted_verbs_are_not():
    current = DiscourseContextBuilder.render(
        "Ellas contestan en voz alta desde el balcón.",
        [turn(64, "La guardia Mara espera.")]
    )
    quoted = DiscourseContextBuilder.render(
        'Mara repite: «Ellas contestan en voz alta» y se marcha.',
        [turn(65, "La guardia Mara espera.")]
    )

    assert "contestan" in current
    assert "Trátalos como comunicación" in current
    assert "Predicado(s) lingüístico(s)" not in quoted



def test_callback_anchor_in_current_segment_does_not_fake_reopening_an_older_topic():
    history = [
        turn(1, "Hablo con Mara sobre el mapa."),
        turn(2, "Cambiando de tema, inspecciono la torre."),
        turn(3, "Busco una entrada junto al faro."),
    ]

    rendered = DiscourseContextBuilder.render(
        "Volviendo a lo del faro, ¿qué encontramos?",
        history,
    )

    assert "sin ancla que coincida con el historial" in rendered
    assert "seleccionan el/los segmentos históricos" not in rendered



def test_typed_discourse_selection_exposes_callback_reason_anchor_and_segment():
    history = [
        turn(70, "Hablo con Mara sobre el mapa."),
        turn(71, "Cambiando de tema, inspecciono la torre."),
        turn(72, "Busco una entrada lateral."),
    ]
    selection = DiscourseContextBuilder.select_history(
        history,
        "Volviendo a lo de Mara, le pregunto por el mapa.",
    )
    assert selection.reason == "callback_anchor_match"
    assert selection.anchor_tokens == ("mara",)
    assert selection.selected_segments == (0,)
    assert selection.candidate_scores == ((0, 1),)
    assert [item.id for item in selection.turns] == [70]
    assert selection.ambiguous is False


def test_surface_pronoun_spans_are_literal_and_quoted_pronouns_are_ignored():
    text = 'Ellas contestan y Mara repite: «ella responde»'
    mentions = DiscourseContextBuilder.surface_pronoun_mentions(text)
    assert [item.text for item in mentions] == ["Ellas"]
    assert mentions[0].gender == "feminine"
    assert mentions[0].number == "plural"
    assert text[mentions[0].start:mentions[0].end] == "Ellas"


def test_subject_linked_speech_signals_exclude_quotes_and_negated_interveners():
    signal = DiscourseContextBuilder.speech_predicate_signals(
        "Ellas contestan en voz alta."
    )
    assert len(signal) == 1
    assert signal[0].subject == "Ellas"
    assert signal[0].predicate == "contestan"
    assert signal[0].gender == "feminine"
    assert signal[0].number == "plural"

    assert DiscourseContextBuilder.speech_predicate_signals(
        'Mara repite: «Ellas contestan» y se marcha.'
    ) == ()
    assert DiscourseContextBuilder.speech_predicate_signals(
        "Ellas no contestan."
    ) == ()



def test_dative_clitics_are_extracted_only_before_supported_finite_verbs():
    text = "Le pregunto por el mapa; después les respondo con calma."
    mentions = DiscourseContextBuilder.surface_pronoun_mentions(text)

    assert [item.text for item in mentions] == ["Le", "les"]
    assert [item.number for item in mentions] == ["singular", "plural"]
    assert all(item.gender == "unknown" for item in mentions)
    assert all(text[item.start:item.end] == item.text for item in mentions)

    assert DiscourseContextBuilder.surface_pronoun_mentions(
        "Miro la puerta y reviso las cartas."
    ) == ()
    assert DiscourseContextBuilder.surface_pronoun_mentions(
        'Mara dice: «Le pregunto por el mapa».'
    ) == ()


def test_named_visible_npc_speech_predicates_require_a_unique_active_alias():
    mara = Entity(id=80, name="Mara", entity_type="npc")
    visible = DiscourseContextBuilder.speech_predicate_signals(
        "Mara responde en voz alta.",
        visible_entities=(mara,),
    )
    assert len(visible) == 1
    assert visible[0].subject == "Mara"
    assert visible[0].predicate == "responde"
    assert visible[0].subject_kind == "visible_npc"
    assert visible[0].gender == "unknown"
    assert visible[0].number == "unknown"

    duplicate = Entity(id=81, name="Mara", entity_type="npc")
    assert DiscourseContextBuilder.speech_predicate_signals(
        "Mara responde en voz alta.",
        visible_entities=(mara, duplicate),
    ) == ()


def test_named_npc_speech_signals_ignore_quotes_and_inactive_entities():
    mara = Entity(id=82, name="Mara", entity_type="npc")
    inactive = Entity(id=83, name="Aldric", entity_type="npc", active=False)

    assert DiscourseContextBuilder.speech_predicate_signals(
        'Mara repite: «Mara responde» y se marcha.',
        visible_entities=(mara,),
    ) == ()
    assert DiscourseContextBuilder.speech_predicate_signals(
        "Aldric responde.",
        visible_entities=(inactive,),
    ) == ()


def test_named_npc_speech_signal_is_rendered_as_a_hint_without_authority():
    mara = Entity(id=84, name="Mara", entity_type="npc")
    rendered = DiscourseContextBuilder.render(
        "Mara responde desde el balcón.",
        (),
        visible_entities=(mara,),
    )

    assert "sujeto='Mara'" in rendered
    assert "tipo=visible_npc" in rendered
    assert "no aporta identidad canónica ni autoridad" in rendered


def test_callback_anchor_excludes_the_following_clause_and_keeps_a_fallback_anchor():
    assert DiscourseContextBuilder._callback_anchor_sequence(
        "Volviendo a lo de Mara, le pregunto por el mapa."
    ) == ("mara",)
    assert "carta" in DiscourseContextBuilder._callback_anchor_sequence(
        "Como te dije antes, quiero continuar con el asunto de la carta."
    )



def test_render_explains_dative_clitics_without_assigning_a_referent():
    rendered = DiscourseContextBuilder.render(
        "Le pregunto por el mapa y les respondo después.",
        (),
    )

    assert "Clítico(s) dativo(s) literal(es)" in rendered
    assert "conserva el clítico literal" in rendered
    assert "asignar identidad" in rendered



def test_negated_speech_predicates_are_not_rendered_as_positive_dialogue_cues():
    mara = Entity(id=85, name="Mara", entity_type="npc")
    for utterance in ("Mara no responde.", "Ellas nunca contestan."):
        rendered = DiscourseContextBuilder.render(
            utterance,
            (),
            visible_entities=(mara,),
        )
        assert "Trátalos como comunicación" not in rendered
        assert "Señal superficial tipada de habla" not in rendered
