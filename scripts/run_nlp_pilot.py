"""Run the offline, content-free Stanza NLP pilot over fixed corpora.

This script is opt-in and requires the optional Stanza package and locally
downloaded Spanish models. It never calls Ollama or changes production prompts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter, process_time
from typing import Any

from services.nlp_pilot.probes import (
    NlpPilotProbeLedger,
    expected_utterance_probes,
    lexical_utterance_probes,
    nearest_rank_percentile,
    parser_utterance_probes,
)
from services.nlp_pilot.stanza_adapter import StanzaParserAdapter


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
CORPORA = {
    "development": "language_understanding_corpus_v1.json",
    "held_out": "language_understanding_corpus_holdout_v1.json",
}


def _load_scenarios(split: str) -> list[tuple[str, dict[str, Any]]]:
    if split not in {"development", "holdout", "both"}:
        raise ValueError("split must be development, holdout or both")
    selected_splits = (
        {"development", "held_out"}
        if split == "both"
        else {"held_out" if split == "holdout" else split}
    )
    scenarios: list[tuple[str, dict[str, Any]]] = []
    for selected_split, filename in CORPORA.items():
        if selected_split not in selected_splits:
            continue
        payload = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
        if not isinstance(payload.get("scenarios"), list):
            raise TypeError(f"{filename} does not contain a scenarios array")
        if selected_split == "held_out" and payload.get("split") != "held_out":
            raise ValueError("held-out corpus split marker is invalid")
        scenarios.extend((selected_split, item) for item in payload["scenarios"])
    return scenarios


def _directory_size_bytes(path: Path) -> int | None:
    if not path.exists() or not path.is_dir():
        return None
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def run(
    *,
    split: str,
    model_dir: Path,
    limit_per_split: int | None,
    adapter: Any | None = None,
) -> dict[str, Any]:
    if adapter is None:
        adapter = StanzaParserAdapter(model_dir=model_dir)
    selected = _load_scenarios(split)
    if limit_per_split is not None:
        counters: Counter[str] = Counter()
        limited: list[tuple[str, dict[str, Any]]] = []
        for item_split, scenario in selected:
            if counters[item_split] >= limit_per_split:
                continue
            counters[item_split] += 1
            limited.append((item_split, scenario))
        selected = limited

    probe_ledger = NlpPilotProbeLedger()
    parse_latencies: list[float] = []
    cpu_latencies: list[float] = []
    errors: Counter[str] = Counter()
    total_words = 0
    total_sentences = 0
    lemma_words = 0
    upos_words = 0
    dependency_words = 0
    attempted = len(selected)
    successful = 0
    cpu_started = process_time()
    wall_started = perf_counter()

    for item_split, scenario in selected:
        text = scenario.get("input")
        if not isinstance(text, str) or not text.strip():
            errors["InvalidCorpusScenario"] += 1
            continue
        expected = expected_utterance_probes(scenario)
        lexical = lexical_utterance_probes(text)
        parsed_probes = None
        case_cpu_started = process_time()
        try:
            document = adapter.parse(text)
        except Exception as exc:  # noqa: BLE001 - count type only; do not emit player text
            errors[type(exc).__name__] += 1
        else:
            successful += 1
            parsed_probes = parser_utterance_probes(document)
            parse_latencies.append(float(document.elapsed_ms))
            total_words += document.word_count
            total_sentences += document.sentence_count
            for sentence in document.sentences:
                for word in sentence.words:
                    lemma_words += int(word.lemma is not None)
                    upos_words += int(word.upos is not None)
                    dependency_words += int(word.dependency is not None)
        cpu_latencies.append((process_time() - case_cpu_started) * 1000)
        probe_ledger.record(
            family=f"{item_split}:{scenario.get('family', 'unclassified')}",
            expected=expected,
            lexical=lexical,
            parser=parsed_probes,
        )

    total_cpu_seconds = process_time() - cpu_started
    total_wall_seconds = perf_counter() - wall_started
    model_bytes = _directory_size_bytes(model_dir.expanduser())
    word_denominator = total_words
    return {
        "schema_version": 1,
        "experiment": "optional_spanish_nlp_parser_pilot",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "corpora": {
            "split": split,
            "scenario_count": attempted,
            "successful_parses": successful,
            "failed_parses": attempted - successful,
            "parse_coverage": (
                round(successful / attempted, 4) if attempted else None
            ),
        },
        "parser": {
            "adapter": getattr(adapter, "adapter_name", "stanza"),
            "language": adapter.language,
            "model_package": adapter.model_package,
            "library_version": adapter.library_version,
            "processors": getattr(
                adapter,
                "processors",
                StanzaParserAdapter.DEFAULT_PROCESSORS,
            ),
            "device": "cpu",
            "model_directory_bytes": model_bytes,
            "model_directory_megabytes": (
                round(model_bytes / (1024 * 1024), 2) if model_bytes is not None else None
            ),
        },
        "structure": {
            "sentence_count": total_sentences,
            "word_count": total_words,
            "lemma_coverage": (
                round(lemma_words / word_denominator, 4) if word_denominator else None
            ),
            "upos_coverage": (
                round(upos_words / word_denominator, 4) if word_denominator else None
            ),
            "dependency_coverage": (
                round(dependency_words / word_denominator, 4)
                if word_denominator else None
            ),
        },
        "performance": {
            "total_wall_seconds": round(total_wall_seconds, 3),
            "total_cpu_seconds": round(total_cpu_seconds, 3),
            "wall_latency_p50_ms": nearest_rank_percentile(parse_latencies, 0.50),
            "wall_latency_p95_ms": nearest_rank_percentile(parse_latencies, 0.95),
            "cpu_latency_p50_ms": nearest_rank_percentile(cpu_latencies, 0.50),
            "cpu_latency_p95_ms": nearest_rank_percentile(cpu_latencies, 0.95),
            "parser_latency_sample_count": len(parse_latencies),
            "cpu_latency_sample_count": len(cpu_latencies),
        },
        "probe_metrics": probe_ledger.summary(),
        "parse_error_types": dict(sorted(errors.items())),
        "privacy": {
            "utterances_persisted": False,
            "raw_parser_tokens_persisted": False,
            "lemmas_persisted": False,
            "entity_names_persisted": False,
            "gold_text_embedded_in_prompts": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an offline parser pilot; no LLM calls are made."
    )
    parser.add_argument(
        "--split",
        choices=("development", "holdout", "both"),
        default="both",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path(
            os.getenv("STANZA_RESOURCES_DIR", str(Path.home() / "stanza_resources"))
        ),
    )
    parser.add_argument("--limit-per-split", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.limit_per_split is not None and args.limit_per_split < 1:
        parser.error("--limit-per-split must be at least 1")

    result = run(
        split=args.split,
        model_dir=args.model_dir.expanduser(),
        limit_per_split=args.limit_per_split,
    )
    serialized = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        target = args.output.expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(serialized, encoding="utf-8")
    sys.stdout.write(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
