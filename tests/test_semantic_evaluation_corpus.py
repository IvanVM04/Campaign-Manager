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
            assert "not be copied" in corpus["description"] or "not prompt" in corpus["description"], corpus_name
        for scenario in corpus["scenarios"]:
            scenario_id = scenario["id"]
            assert scenario_id not in identifiers, scenario_id
            identifiers.add(scenario_id)
            assert isinstance(scenario.get("critical"), bool) if "critical" in scenario else held_out
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
