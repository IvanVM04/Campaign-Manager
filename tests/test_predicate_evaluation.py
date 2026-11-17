"""Offline tests for action/relation predicate scoring and report safety."""

import json
from types import SimpleNamespace

from tests.semantic_evaluation_metrics import SemanticEvaluationLedger
from tests.semantic_evaluation_report import (
    build_live_evaluation_report,
    write_live_evaluation_report,
)
from tests.semantic_frame_evaluation import score_semantic_frame_scenario


def _frame(predicate: str, family: str = "transfer"):
    return SimpleNamespace(
        predicate=predicate,
        family=SimpleNamespace(value=family),
        arguments=(),
    )


def _analysis(*, frames=(), claims=()):
    return SimpleNamespace(
        steps=tuple(SimpleNamespace(action_frame=frame) for frame in frames),
        relation_claims=tuple(claims),
    )


def test_action_predicate_surface_is_scored_independently_of_frame_family():
    scenario = {
        "id": "action-predicate-01",
        "expected_action_frame": {
            "predicate": "Entrego",
            "family": "transfer",
            "arguments": [],
        },
    }
    ledger = SemanticEvaluationLedger()
    matched, total, failures = score_semantic_frame_scenario(
        _analysis(frames=(_frame("Entrego", "other"),)),
        scenario,
        ledger=ledger,
    )

    assert matched == 2
    assert total == 3
    assert len(failures) == 1
    assert failures[0].startswith("action_frame.family:")
    report = ledger.summary()
    family = report["families"]["predicate_surface:action_frame_predicate_surface"]
    quality = report["semantic_slot_quality"]["action_frame_predicate_surface"]
    assert family["case_accuracy"] == 1.0
    assert quality["f1"] == 1.0


def test_action_predicate_inflection_mismatch_is_reported_even_when_frame_is_valid():
    scenario = {
        "id": "action-predicate-02",
        "expected_action_frame": {
            "predicate": "Entrego",
            "family": "transfer",
            "arguments": [],
        },
    }
    ledger = SemanticEvaluationLedger()
    matched, total, failures = score_semantic_frame_scenario(
        _analysis(frames=(_frame("entregar"),)),
        scenario,
        ledger=ledger,
    )

    assert matched == 2  # frame existence and family pass; the predicate does not
    assert total == 3
    assert any(item.startswith("action_frame.predicate:") for item in failures)
    metrics = ledger.summary()["semantic_slot_quality"][
        "action_frame_predicate_surface"
    ]
    assert metrics["precision"] == 0.0
    assert metrics["recall"] == 0.0
    assert metrics["f1"] == 0.0


def test_relation_predicate_surface_is_independent_of_relation_direction():
    claim = SimpleNamespace(
        subject=SimpleNamespace(text="la guardia"),
        object=SimpleNamespace(text="Mara"),
        predicate="trabaja",
        relation_family=SimpleNamespace(value="membership"),
        polarity=SimpleNamespace(value="positive"),
        modality=SimpleNamespace(value="completed"),
        source_excerpt="Bram pertenece al gremio de cartógrafos.",
        attributed_to=None,
        temporal_expression=None,
    )
    scenario = {
        "id": "relation-predicate-01",
        "expected_relation": {
            "subject": "Mara",
            "object": "la guardia",
            "predicate": "trabaja",
            "relation_family": "employment",
            "polarity": "positive",
        },
    }
    ledger = SemanticEvaluationLedger()
    matched, total, failures = score_semantic_frame_scenario(
        _analysis(claims=(claim,)),
        scenario,
        ledger=ledger,
    )

    assert matched == 1  # exact predicate matches although endpoint direction is wrong
    assert total == 4
    assert any(item.startswith("relation direction:") for item in failures)
    assert not any(item.startswith("relation.predicate:") for item in failures)
    metrics = ledger.summary()["semantic_slot_quality"]["relation_predicate_surface"]
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["f1"] == 1.0


def test_missing_action_predicate_is_a_false_negative():
    scenario = {
        "id": "action-predicate-03",
        "expected_action_frame": {
            "predicate": "Camino",
            "family": "movement",
            "arguments": [],
        },
    }
    ledger = SemanticEvaluationLedger()
    score_semantic_frame_scenario(None, scenario, ledger=ledger)

    metrics = ledger.summary()["semantic_slot_quality"]["action_frame_predicate_surface"]
    assert metrics["true_positive"] == 0
    assert metrics["false_negative"] == 1
    assert metrics["f1"] == 0.0


def test_live_evaluation_report_contains_reproducibility_and_omits_free_text(
    tmp_path,
    monkeypatch,
):
    class Provider:
        model = "gemma4:12b-it-q4_K_M"
        timeout = 900.0
        think = False

        def get_model_digest(self):
            return "sha256:example"

        def get_server_version(self):
            return "0.40.16"

    ledger = SemanticEvaluationLedger()
    ledger.record_case(
        "predicate_surface:action",
        expected_slots=1,
        matched_slots=1,
        elapsed_seconds=0.1,
    )
    report = build_live_evaluation_report(
        evaluation_name="semantic_frame_predicate_holdout",
        corpus_name="semantic_frame_corpus_holdout_v1.json",
        provider=Provider(),
        ledger=ledger,
        scenario_count=20,
        provider_calls=22,
        elapsed_seconds=123.456,
        usage_events=[{
            "provider_model": "gemma4:12b-it-q4_K_M",
            "duration_ms": 100,
            "prompt": "private prompt",
            "completion": "private completion",
        }],
        scenario_filter="holdout-transfer-scroll",
    )
    monkeypatch.delenv("CAMPAIGN_MANAGER_REAL_LLM_REPORT_PATH", raising=False)
    path = tmp_path / "nested" / "report.json"
    written = write_live_evaluation_report(report, path=path)

    assert written == str(path)
    serialized = path.read_text(encoding="utf-8")
    assert "sha256:example" in serialized
    assert "0.40.16" in serialized
    assert "private prompt" not in serialized
    assert "private completion" not in serialized
    assert '"provider_model": "gemma4:12b-it-q4_K_M"' in serialized
    loaded = json.loads(serialized)
    assert loaded["metadata"]["timeout_seconds"] == 900.0
    assert loaded["metadata"]["think"] is False
