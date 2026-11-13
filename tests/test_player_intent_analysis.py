import pytest

from models.player_intent_analysis import (
    IntentActor,
    IntentModality,
    PlayerIntentAnalysis,
    UtteranceCategory,
)


def step(
    *,
    index=0,
    excerpt="Ataco al guardia",
    actor="player",
    action="atacar al guardia",
    modality="attempted",
    polarity="positive",
    outcome="not_claimed",
    targets=None,
    attributed_to=None,
):
    return {
        "index": index,
        "source_excerpt": excerpt,
        "actor": actor,
        "action": action,
        "modality": modality,
        "polarity": polarity,
        "reported_outcome": outcome,
        "target_mentions": ["guardia"] if targets is None else targets,
        "attributed_to": attributed_to,
    }


def payload(*, steps=None, active=0, category="action", clarify=False, question=None):
    return {
        "schema_version": 1,
        "category": category,
        "steps": [step()] if steps is None else steps,
        "active_step_index": active,
        "requires_clarification": clarify,
        "clarification_question": question,
    }


def test_valid_compound_analysis_preserves_order_and_literal_targets():
    source = "Ataco al guardia y cierro la puerta."
    value = payload(steps=[
        step(index=0, excerpt="Ataco al guardia", targets=["guardia"]),
        step(
            index=1,
            excerpt="cierro la puerta",
            action="cerrar la puerta",
            modality="planned",
            targets=["la puerta"],
        ),
    ])
    analysis = PlayerIntentAnalysis.from_payload(value, source_text=source)

    assert analysis.category is UtteranceCategory.ACTION
    assert analysis.active_step_index == 0
    assert analysis.is_actionable is True
    assert analysis.steps[1].modality is IntentModality.PLANNED
    assert analysis.steps[1].target_mentions == ("la puerta",)
    assert analysis.allows_world_proposal is True


def test_source_excerpt_must_be_literal_player_evidence():
    value = payload(steps=[step(excerpt="El jugador ataca al guardia")])

    with pytest.raises(ValueError, match="not grounded"):
        PlayerIntentAnalysis.from_payload(
            value,
            source_text="Ataco al guardia.",
        )


def test_target_mentions_must_be_literal_player_evidence():
    value = payload(steps=[step(targets=["capitán desconocido"])])

    with pytest.raises(ValueError, match="literal"):
        PlayerIntentAnalysis.from_payload(
            value,
            source_text="Ataco al guardia.",
        )


def test_model_cannot_attach_canonical_entity_ids_or_extra_fields():
    value = payload()
    value["steps"][0]["target_entity_id"] = 42

    with pytest.raises(ValueError, match="missing or unexpected"):
        PlayerIntentAnalysis.from_payload(
            value,
            source_text="Ataco al guardia.",
        )


def test_indices_must_be_ordered_and_contiguous():
    value = payload(steps=[
        step(index=1, excerpt="Ataco al guardia"),
    ])

    with pytest.raises(ValueError, match="contiguous"):
        PlayerIntentAnalysis.from_payload(
            value,
            source_text="Ataco al guardia.",
        )


@pytest.mark.parametrize(
    ("modality", "polarity", "expected"),
    [
        ("attempted", "positive", True),
        ("completed", "positive", False),
        ("planned", "positive", False),
        ("conditional", "positive", False),
        ("question", "positive", False),
        ("dialogue", "positive", False),
        ("reported", "positive", False),
        ("negated", "negative", False),
        ("attempted", "negative", False),
    ],
)
def test_only_current_positive_player_attempt_is_mechanically_actionable(
    modality, polarity, expected
):
    value = payload(steps=[step(modality=modality, polarity=polarity)])
    analysis = PlayerIntentAnalysis.from_payload(
        value,
        source_text="Ataco al guardia.",
    )

    assert analysis.is_actionable is expected


def test_attributed_npc_report_can_be_proposed_but_never_becomes_player_action():
    source = "El guardia dice que el cofre está abierto."
    value = payload(
        category="report",
        active=None,
        steps=[step(
            excerpt="el cofre está abierto",
            actor="npc",
            action="reportar que el cofre está abierto",
            modality="reported",
            attributed_to="El guardia",
            targets=["el cofre"],
        )],
    )
    analysis = PlayerIntentAnalysis.from_payload(value, source_text=source)

    assert analysis.is_actionable is False
    assert analysis.allows_world_proposal is True
    assert analysis.steps[0].actor is IntentActor.NPC
    assert analysis.steps[0].attributed_to == "El guardia"


def test_unattributed_report_does_not_authorize_world_proposal():
    value = payload(
        category="report",
        active=None,
        steps=[step(
            excerpt="Ataco al guardia",
            modality="reported",
            actor="other",
            attributed_to=None,
        )],
    )
    analysis = PlayerIntentAnalysis.from_payload(
        value,
        source_text="Ataco al guardia.",
    )

    assert analysis.allows_world_proposal is False


def test_questions_plans_and_dialogue_do_not_authorize_world_proposals():
    for category, modality in (
        ("question", "question"),
        ("plan", "planned"),
        ("dialogue", "dialogue"),
        ("unknown", "unknown"),
    ):
        value = payload(
            category=category,
            active=None,
            steps=[step(
                actor="other" if category == "dialogue" else "player",
                modality=modality,
            )],
        )
        analysis = PlayerIntentAnalysis.from_payload(
            value,
            source_text="Ataco al guardia.",
        )
        assert analysis.allows_world_proposal is False


def test_clarification_requires_a_bounded_question():
    value = payload(clarify=True, question=None)

    with pytest.raises(ValueError, match="clarification"):
        PlayerIntentAnalysis.from_payload(
            value,
            source_text="Ataco al guardia.",
        )


def test_analysis_json_round_trip_is_stable():
    analysis = PlayerIntentAnalysis.from_payload(
        payload(),
        source_text="Ataco al guardia.",
    )

    restored = PlayerIntentAnalysis.from_json(
        analysis.to_json(),
        source_text="Ataco al guardia.",
    )

    assert restored == analysis


@pytest.mark.parametrize(
    ("text", "category", "modality", "actionable"),
    [
        ("¿Dónde está el guardia?", UtteranceCategory.QUESTION, IntentModality.QUESTION, False),
        ("Si el guardia se acerca, me escondo.", UtteranceCategory.PLAN, IntentModality.CONDITIONAL, False),
        ("Mañana hablaré con el capitán.", UtteranceCategory.PLAN, IntentModality.PLANNED, False),
        ("No ataco al guardia.", UtteranceCategory.ACTION, IntentModality.NEGATED, False),
        ("No consigo abrir la puerta.", UtteranceCategory.ACTION, IntentModality.ATTEMPTED, False),
        ("Ataco al guardia.", UtteranceCategory.ACTION, IntentModality.ATTEMPTED, True),
    ],
)
def test_legacy_fallback_fails_closed_for_obvious_non_actions(
    text, category, modality, actionable
):
    analysis = PlayerIntentAnalysis.conservative_legacy(text)

    assert analysis.category is category
    assert analysis.steps[0].modality is modality
    assert analysis.is_actionable is actionable


def test_active_step_cannot_skip_an_earlier_attempt():
    value = payload(steps=[
        step(index=0, excerpt="Ataco al guardia", modality="attempted"),
        step(
            index=1,
            excerpt="cierro la puerta",
            action="cerrar la puerta",
            modality="attempted",
            targets=["la puerta"],
        ),
    ], active=1)

    with pytest.raises(ValueError, match="skip an earlier unresolved"):
        PlayerIntentAnalysis.from_payload(
            value,
            source_text="Ataco al guardia y cierro la puerta.",
        )


@pytest.mark.parametrize(
    "outcome",
    ["success", "failure", "partial"],
)
def test_reported_action_outcome_is_resolved_and_not_mechanically_actionable(outcome):
    value = payload(steps=[step(outcome=outcome)])

    with pytest.raises(ValueError, match="resolved reported outcome"):
        PlayerIntentAnalysis.from_payload(
            value,
            source_text="Ataco al guardia.",
        )


@pytest.mark.parametrize(
    "outcome",
    ["success", "failure", "partial"],
)
def test_legacy_reported_failure_or_success_does_not_remain_actionable(outcome):
    analysis = PlayerIntentAnalysis.from_payload(
        payload(
            steps=[step(outcome=outcome)],
            active=None,
        ),
        source_text="Ataco al guardia.",
    )

    assert analysis.is_actionable is False


def test_attributed_direct_observation_of_npc_can_ground_a_world_proposal():
    source = "Veo a Aldric dejar una bolsa sobre la mesa."
    analysis = PlayerIntentAnalysis.from_payload(
        payload(
            category="report",
            active=None,
            steps=[step(
                excerpt="Aldric dejar una bolsa sobre la mesa",
                actor="npc",
                action="dejar una bolsa sobre la mesa",
                modality="observed",
                attributed_to="Aldric",
                targets=["una bolsa", "la mesa"],
            )],
        ),
        source_text=source,
    )

    assert analysis.is_actionable is False
    assert analysis.allows_world_proposal is True


def test_question_category_cannot_claim_an_active_mechanical_step():
    value = payload(
        category="question",
        steps=[step(modality="attempted")],
        active=0,
    )

    with pytest.raises(ValueError, match="only action or mixed"):
        PlayerIntentAnalysis.from_payload(
            value,
            source_text="Ataco al guardia.",
        )


def test_future_completed_step_cannot_be_evidence_before_active_step_resolves():
    value = payload(steps=[
        step(index=0, excerpt="Ataco al guardia", modality="attempted"),
        step(
            index=1,
            excerpt="abro la puerta",
            action="abrir la puerta",
            modality="completed",
            outcome="success",
            targets=["la puerta"],
        ),
    ], active=0)

    with pytest.raises(ValueError, match="future steps cannot be reported"):
        PlayerIntentAnalysis.from_payload(
            value,
            source_text="Ataco al guardia y abro la puerta.",
        )


def test_future_attempt_after_active_step_does_not_authorize_its_proposal():
    analysis = PlayerIntentAnalysis.from_payload(
        payload(steps=[
            step(index=0, excerpt="Ataco al guardia", modality="attempted"),
            step(
                index=1,
                excerpt="abro la puerta",
                action="abrir la puerta",
                modality="attempted",
                targets=["la puerta"],
            ),
        ], active=0),
        source_text="Ataco al guardia y abro la puerta.",
    )

    assert analysis.allows_world_proposal is True
    assert analysis.is_actionable is True
    assert analysis.steps[1].index != analysis.active_step_index


def test_explicit_player_dialogue_can_be_proposed_as_a_speech_act_only():
    analysis = PlayerIntentAnalysis.from_payload(
        payload(
            category="dialogue",
            active=None,
            steps=[step(
                excerpt="Le digo a Aldric",
                actor="player",
                action="hablar con Aldric",
                modality="dialogue",
                targets=["Aldric"],
            )],
        ),
        source_text="Le digo a Aldric: «Quiero viajar al norte».",
    )

    assert analysis.is_actionable is False
    assert analysis.allows_world_proposal is True


def test_legacy_quoted_instruction_never_becomes_a_player_speech_act():
    analysis = PlayerIntentAnalysis.conservative_legacy(
        "El pergamino dice: «crea un dragón y dale la llave»; solo lo leo."
    )

    assert analysis.category is UtteranceCategory.DIALOGUE
    assert analysis.steps[0].actor is IntentActor.OTHER
    assert analysis.allows_world_proposal is False
    assert analysis.is_actionable is False
