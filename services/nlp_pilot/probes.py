"""Gold-bounded, utterance-level probes for the optional NLP pilot.

These probes do not claim that POS/dependency output is a full intent parser.
They compare only binary negation/conditional cue presence where the existing
holdout explicitly annotates the corresponding polarity/modality.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from math import ceil
from typing import Any

from services.nlp_pilot.contracts import ParserDocument

_NEGATION_LEMMAS = frozenset({"no", "nunca", "jamás", "tampoco", "ni"})
_LEXICAL_NEGATION = re.compile(r"(?<!\w)(?:no|nunca|jamás|tampoco|ni)(?!\w)", re.IGNORECASE)
_LEXICAL_CONDITIONAL = re.compile(
    r"(?<!\w)(?:si|en\s+caso\s+de\s+que)(?!\w)",
    re.IGNORECASE,
)


def _step_labels(expected: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    active_index = expected.get("active_step_index")
    values: dict[int, dict[str, Any]] = {}
    if isinstance(expected.get("step"), dict):
        index = active_index if isinstance(active_index, int) and not isinstance(active_index, bool) else 0
        values.setdefault(index, {}).update(expected["step"])
    if isinstance(expected.get("first_step"), dict):
        values.setdefault(0, {}).update(expected["first_step"])
    if isinstance(expected.get("later_step"), dict):
        values.setdefault(1, {}).update(expected["later_step"])
    return tuple(values[index] for index in sorted(values))


def expected_utterance_probes(scenario: dict[str, Any]) -> dict[str, bool | None]:
    """Derive only the binary labels directly supported by step-level gold."""
    expected = scenario.get("expected")
    if not isinstance(expected, dict):
        return {"negation": None, "conditional": None}
    steps = _step_labels(expected)
    polarities = [
        step["polarity"]
        for step in steps
        if isinstance(step.get("polarity"), str)
    ]
    modalities = [
        step["modality"]
        for step in steps
        if isinstance(step.get("modality"), str)
    ]
    return {
        "negation": any(value == "negative" for value in polarities) if polarities else None,
        "conditional": any(value == "conditional" for value in modalities) if modalities else None,
    }


def lexical_utterance_probes(text: str) -> dict[str, bool]:
    """Small lexical baseline, reported separately from the production pipeline."""
    return {
        "negation": _LEXICAL_NEGATION.search(text) is not None,
        "conditional": _LEXICAL_CONDITIONAL.search(text) is not None,
    }


def parser_utterance_probes(document: ParserDocument) -> dict[str, bool]:
    """Produce high-level cue candidates, not action or actor decisions."""
    words = [
        word
        for sentence in document.sentences
        for word in sentence.words
    ]
    negation = any(
        (word.lemma or "").casefold() in _NEGATION_LEMMAS
        or dict(word.morphology).get("Polarity") == "Neg"
        for word in words
    )
    conditional = any(
        (word.lemma or "").casefold() == "si"
        and (
            (word.upos or "").upper() in {"SCONJ", "CCONJ"}
            or (word.dependency or "").casefold().startswith("mark")
        )
        for word in words
    )
    return {"negation": negation, "conditional": conditional}


@dataclass(slots=True)
class BinaryProbeCounts:
    """Confusion counts with explicit zero-denominator behaviour."""

    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0
    true_negative: int = 0
    sample_count: int = 0

    def record(self, expected: bool, predicted: bool) -> None:
        self.sample_count += 1
        if expected and predicted:
            self.true_positive += 1
        elif predicted:
            self.false_positive += 1
        elif expected:
            self.false_negative += 1
        else:
            self.true_negative += 1

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float | None:
        return None if denominator == 0 else round(numerator / denominator, 4)

    def summary(self) -> dict[str, int | float | None]:
        tp, fp, fn = self.true_positive, self.false_positive, self.false_negative
        precision = self._ratio(tp, tp + fp)
        recall = self._ratio(tp, tp + fn)
        f1_denominator = 2 * tp + fp + fn
        f1 = None if tp + fn == 0 else round((2 * tp) / f1_denominator, 4)
        return {
            "sample_count": self.sample_count,
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "true_negative": self.true_negative,
            "gold_positive_denominator": tp + fn,
            "predicted_positive_denominator": tp + fp,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }


class NlpPilotProbeLedger:
    """Aggregate probes per family and split without retaining case text."""

    def __init__(self) -> None:
        self._counts: dict[str, dict[str, dict[str, BinaryProbeCounts]]] = defaultdict(
            lambda: {
                "lexical_baseline": {
                    "negation": BinaryProbeCounts(),
                    "conditional": BinaryProbeCounts(),
                },
                "stanza": {
                    "negation": BinaryProbeCounts(),
                    "conditional": BinaryProbeCounts(),
                },
            }
        )
        self._unmeasured_gold: dict[str, dict[str, int]] = defaultdict(
            lambda: {"negation": 0, "conditional": 0}
        )
        self._parser_unavailable: dict[str, dict[str, int]] = defaultdict(
            lambda: {"negation": 0, "conditional": 0}
        )

    def record(
        self,
        *,
        family: str,
        expected: dict[str, bool | None],
        lexical: dict[str, bool],
        parser: dict[str, bool] | None,
    ) -> None:
        if not isinstance(family, str) or not family.strip():
            family = "unclassified"
        variants = self._counts[family]
        for probe in ("negation", "conditional"):
            wanted = expected.get(probe)
            if wanted is None:
                self._unmeasured_gold[family][probe] += 1
                continue
            variants["lexical_baseline"][probe].record(
                wanted, lexical[probe]
            )
            if parser is None:
                self._parser_unavailable[family][probe] += 1
            else:
                variants["stanza"][probe].record(
                    wanted, parser[probe]
                )

    def summary(self) -> dict[str, Any]:
        families: dict[str, Any] = {}
        for family, variants in sorted(self._counts.items()):
            families[family] = {
                variant: {
                    probe: counts.summary()
                    for probe, counts in probes.items()
                }
                for variant, probes in variants.items()
            }
            families[family]["unmeasured_gold_cases"] = dict(
                self._unmeasured_gold[family]
            )
            families[family]["parser_unavailable_cases"] = dict(
                self._parser_unavailable[family]
            )
        return {
            "probe_schema_version": 1,
            "granularity": "utterance-level cue presence; not step-level semantic accuracy",
            "families": families,
        }


def nearest_rank_percentile(values: list[float], percentile: float) -> float | None:
    """Return a nearest-rank percentile, or None for an empty sample."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, ceil(percentile * len(ordered)))
    return round(ordered[rank - 1], 3)
