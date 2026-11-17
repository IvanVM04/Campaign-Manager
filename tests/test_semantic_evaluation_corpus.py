"""Integrity checks for the development and held-out language corpora."""

import json
from collections import Counter
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
CORPORA = (
    ("utterance-development", "language_understanding_corpus_v1.json", False),
    ("utterance-held-out", "language_understanding_corpus_holdout_v1.json", True),
    ("semantic-frame-development", "semantic_frame_corpus_v1.json", False),
    ("semantic-frame-held-out", "semantic_frame_corpus_holdout_v1.json", True),
    ("discourse-development", "conversation_understanding_corpus_v2.json", False),
    ("discourse-held-out", "conversation_understanding_corpus_holdout_v1.json", True),
    ("discourse-pipeline-held-out", "discourse_pipeline_corpus_holdout_v1.json", True),
)


def _read(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_semantic_evaluation_corpus_has_at_least_one_hundred_unique_cases():
    total = 0
    identifiers: set[str] = set()
    family_counts: Counter[str] = Counter()

    for corpus_name, path, held_out in CORPORA:
        corpus = _read(path)
        assert corpus["schema_version"] in {1, 2}, corpus_name
        assert isinstance(corpus["scenarios"], list), corpus_name
        if held_out:
            assert corpus["split"] == "held_out", corpus_name
            assert any(
                marker in corpus["description"].casefold()
                for marker in ("reserved for measurement", "not be copied", "do not turn", "not prompt")
            ), corpus_name
        for scenario in corpus["scenarios"]:
            scenario_id = scenario["id"]
            scoped_id = f"{corpus_name}:{scenario_id}"
            assert scoped_id not in identifiers, scoped_id
            identifiers.add(scoped_id)
            if held_out:
                assert isinstance(scenario.get("critical"), bool), scenario_id
            elif "critical" in scenario:
                assert isinstance(scenario["critical"], bool), scenario_id
            if held_out:
                family = scenario.get("family")
                assert isinstance(family, str) and family.strip(), scenario_id
                family_counts[family] += 1
                if "input" in scenario:
                    assert scenario["input"].strip(), scenario_id
                if "utterance" in scenario:
                    assert scenario["utterance"].strip(), scenario_id
        total += len(corpus["scenarios"])

    assert total >= 100
    assert len(identifiers) == total
    assert len(family_counts) >= 10
    assert sum(family_counts.values()) >= 50


def test_held_out_scenarios_are_not_repeated_across_evaluation_families():
    seen: dict[str, str] = {}
    for corpus_name, path, held_out in CORPORA:
        if not held_out:
            continue
        for scenario in _read(path)["scenarios"]:
            utterance = scenario.get("input") or scenario.get("utterance")
            normalized = " ".join(utterance.casefold().split())
            previous = seen.get(normalized)
            assert previous is None, f"{scenario['id']} duplicates {previous}"
            seen[normalized] = scenario["id"]


def test_context_recall_and_secret_exclusion_are_measured_separately(record_property):
    from models.campaign_state import CampaignState
    from models.turn_context import TurnContext
    from services.context import ContextBuilder
    from services.llm_world.llm_world_context_renderer import (
        LLMWorldContextRenderer,
    )
    from tests.context_scale_test_support import build_large_campaign_world
    from tests.semantic_evaluation_metrics import SemanticEvaluationLedger

    world = build_large_campaign_world(entity_count=750)
    context = TurnContext(
        campaign=CampaignState(
            name="La guardia de Puerto Gris",
            current_location_id=2,
            summary="Investigación en una ciudad portuaria.",
        ),
        current_session=None,
        active_character=None,
        active_character_entity=world.entities[1],
        world=world,
    )
    projection = ContextBuilder().build_proposal_context(
        world,
        "Fungoso",
        max_estimated_tokens=5000,
        mandatory_entity_ids=(1, 2),
    )
    rendered = json.dumps(
        LLMWorldContextRenderer.build_context(context, projection),
        ensure_ascii=False,
    )
    ledger = SemanticEvaluationLedger()
    ledger.record_context_recall(
        expected_entity_ids=(1, 2),
        retrieved_entity_ids=projection.world.entities,
    )
    ledger.record_secret_visibility(
        rendered,
        (
            "ruta secreta de contrabando",
            "La capitana trabaja para los contrabandistas",
            "Los guardias protegen la ruta oculta",
        ),
    )
    ledger.emit(record_property, prefix="semantic_context")

    summary = ledger.summary()
    assert summary["context_recall"] == 1.0
    assert summary["secret_leaks"] == 0
    assert "Fungoso recibe aviso: cambio de turno de la guardia" in rendered
    assert "ruta secreta de contrabando" not in rendered
    assert "La capitana trabaja para los contrabandistas" not in rendered
    assert "Los guardias protegen la ruta oculta" not in rendered



def test_semantic_frame_predicate_gold_sidecar_covers_immutable_holdout():
    """Predicate labels extend measurements without mutating held-out utterances."""
    corpus = _read("semantic_frame_corpus_holdout_v1.json")
    annotations = _read("semantic_frame_predicate_gold_v1.json")

    assert corpus["schema_version"] == 1
    assert corpus["split"] == "held_out"
    assert annotations["schema_version"] == 1
    assert annotations["split"] == "held_out_annotations"
    assert annotations["source_corpus"] == "semantic_frame_corpus_holdout_v1.json"
    assert "utterance" not in annotations["description"].casefold()

    source_by_id = {item["id"]: item for item in corpus["scenarios"]}
    annotation_by_id = {item["id"]: item for item in annotations["scenarios"]}
    assert len(annotation_by_id) == len(annotations["scenarios"])
    assert set(annotation_by_id) == set(source_by_id)
    assert len(annotations["scenarios"]) == 20

    action_count = relation_count = 0
    for scenario_id, source in source_by_id.items():
        annotation = annotation_by_id[scenario_id]
        assert "input" not in annotation
        assert "utterance" not in annotation
        if source.get("expected_action_frame") is not None:
            predicate = annotation.get("action_frame_predicate")
            assert isinstance(predicate, str) and predicate
            assert predicate in source["input"]
            action_count += 1
        else:
            assert "action_frame_predicate" not in annotation
        if source.get("expected_relation") is not None:
            predicate = annotation.get("relation_predicate")
            assert isinstance(predicate, str) and predicate
            assert predicate in source["input"]
            relation_count += 1
        else:
            assert "relation_predicate" not in annotation

    assert action_count == 10
    assert relation_count == 10
