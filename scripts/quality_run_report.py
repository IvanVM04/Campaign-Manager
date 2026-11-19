"""Safe, consolidated metrics for one Campaign Manager quality run."""
from __future__ import annotations

import argparse
import json
import math
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def junit_summary(path: Path | None) -> dict[str, Any] | None:
    """Read aggregate JUnit counts only; never read failure messages or output."""
    if path is None or not path.is_file():
        return None
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {"available": False}
    cases = list(root.iter("testcase"))
    failures = errors = skipped = 0
    duration = 0.0
    failed_names: list[str] = []
    for case in cases:
        duration += max(0.0, _number(case.attrib.get("time")) or 0.0)
        case_failed = False
        for child in case:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "failure":
                failures += 1
                case_failed = True
            elif tag == "error":
                errors += 1
                case_failed = True
            elif tag == "skipped":
                skipped += 1
        if case_failed:
            class_name = case.attrib.get("classname", "")
            test_name = case.attrib.get("name", "unknown")
            failed_names.append(f"{class_name}::{test_name}" if class_name else test_name)
    return {
        "available": True,
        "tests": len(cases),
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "passed": max(0, len(cases) - failures - errors - skipped),
        "duration_seconds": round(duration, 3),
        "failed_tests": sorted(set(failed_names)),
    }


def coverage_summary(path: Path | None) -> dict[str, Any] | None:
    """Use the same combined line/branch denominator as the CI coverage gate."""
    if path is None or not path.is_file():
        return None
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {"available": False}
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for class_node in root.findall(".//class"):
        parts = Path(class_node.attrib.get("filename", "")).parts
        package = parts[0] if len(parts) > 1 else "(root)"
        values = totals[package]
        for line in class_node.findall("./lines/line"):
            values[1] += 1
            if int(line.attrib.get("hits", "0")) > 0:
                values[0] += 1
            if line.attrib.get("branch") == "true":
                try:
                    pair = line.attrib.get("condition-coverage", "").split("(", 1)[1].split(")", 1)[0]
                    covered, valid = (int(item) for item in pair.split("/", 1))
                except (IndexError, ValueError):
                    continue
                values[2] += covered
                values[3] += valid
    line_hit = sum(value[0] for value in totals.values())
    line_valid = sum(value[1] for value in totals.values())
    branch_hit = sum(value[2] for value in totals.values())
    branch_valid = sum(value[3] for value in totals.values())
    denominator = line_valid + branch_valid
    combined = 100.0 * (line_hit + branch_hit) / denominator if denominator else 100.0
    return {
        "available": True,
        "lines_covered": line_hit,
        "lines_valid": line_valid,
        "line_percent": round(100.0 * line_hit / line_valid, 2) if line_valid else 100.0,
        "branches_covered": branch_hit,
        "branches_valid": branch_valid,
        "branch_percent": round(100.0 * branch_hit / branch_valid, 2) if branch_valid else None,
        "combined_percent": round(combined, 2),
        "gate_percent": 85.0,
        "gate_passed": combined >= 85.0,
        "packages": [
            {
                "name": name,
                "lines_covered": val[0],
                "lines_valid": val[1],
                "branches_covered": val[2],
                "branches_valid": val[3],
                "combined_percent": round(100.0 * (val[0] + val[2]) / (val[1] + val[3]), 2)
                if val[1] + val[3] else 100.0,
            }
            for name, val in sorted(totals.items())
        ],
    }


def _binary_metrics(counts: dict[str, Any]) -> dict[str, Any]:
    tp = int(counts.get("true_positive", 0) or 0)
    fp = int(counts.get("false_positive", 0) or 0)
    fn = int(counts.get("false_negative", 0) or 0)
    tn = int(counts.get("true_negative", 0) or 0)
    predicted = tp + fp
    gold = tp + fn
    f1_denominator = 2 * tp + fp + fn
    return {
        "samples": int(counts.get("sample_count", tp + fp + fn + tn) or 0),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(tp / predicted, 4) if predicted else None,
        "recall": round(tp / gold, 4) if gold else None,
        "f1": round((2 * tp) / f1_denominator, 4) if f1_denominator else None,
    }


def nlp_offline_summary(path: Path | None) -> dict[str, Any] | None:
    report = _read_json(path)
    if report is None:
        return None
    corpora = report.get("corpora") if isinstance(report.get("corpora"), dict) else {}
    parser = report.get("parser") if isinstance(report.get("parser"), dict) else {}
    perf = report.get("performance") if isinstance(report.get("performance"), dict) else {}
    probe = report.get("probe_metrics") if isinstance(report.get("probe_metrics"), dict) else {}
    families = probe.get("families") if isinstance(probe.get("families"), dict) else {}
    variants = ("lexical_baseline", "stanza")
    aggregate: dict[str, dict[str, dict[str, int]]] = {
        variant: {
            cue: {"sample_count": 0, "true_positive": 0, "false_positive": 0,
                  "false_negative": 0, "true_negative": 0}
            for cue in ("negation", "conditional")
        } for variant in variants
    }
    for family in families.values():
        if not isinstance(family, dict):
            continue
        for variant in variants:
            variant_data = family.get(variant)
            if not isinstance(variant_data, dict):
                continue
            for cue in ("negation", "conditional"):
                values = variant_data.get(cue)
                if not isinstance(values, dict):
                    continue
                for key in aggregate[variant][cue]:
                    aggregate[variant][cue][key] += int(values.get(key, 0) or 0)
    return {
        "available": True,
        "split": corpora.get("split"),
        "scenario_count": corpora.get("scenario_count"),
        "successful_parses": corpora.get("successful_parses"),
        "failed_parses": corpora.get("failed_parses"),
        "parse_coverage": corpora.get("parse_coverage"),
        "model_directory_bytes": parser.get("model_directory_bytes"),
        "model_directory_megabytes": parser.get("model_directory_megabytes"),
        "model_package": parser.get("model_package"),
        "library_version": parser.get("library_version"),
        "wall_latency_p50_ms": perf.get("wall_latency_p50_ms"),
        "wall_latency_p95_ms": perf.get("wall_latency_p95_ms"),
        "cpu_latency_p50_ms": perf.get("cpu_latency_p50_ms"),
        "cpu_latency_p95_ms": perf.get("cpu_latency_p95_ms"),
        "cue_metrics": {
            variant: {cue: _binary_metrics(values) for cue, values in cues.items()}
            for variant, cues in aggregate.items()
        },
        "parse_error_types": report.get("parse_error_types", {}),
    }


def nlp_ab_summary(path: Path | None) -> dict[str, Any] | None:
    report = _read_json(path)
    if report is None:
        return None
    comparison = report.get("comparison")
    if not isinstance(comparison, dict):
        return {"available": True, "comparison_available": False}
    result: dict[str, Any] = {"available": True, "comparison_available": True}
    metadata = report.get("metadata") if isinstance(report.get("metadata"), dict) else {}
    result["metadata"] = {
        key: metadata[key]
        for key in (
            "model", "model_digest", "ollama_version", "timeout_seconds",
            "think", "scenario_count", "provider_calls", "elapsed_seconds",
            "hardware_label",
        )
        if key in metadata
    }
    for variant in ("model_only", "model_plus_stanza_hints"):
        payload = comparison.get(variant)
        if not isinstance(payload, dict):
            continue
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        families = metrics.get("families") if isinstance(metrics.get("families"), dict) else {}
        case_count = sum(
            int(item.get("cases", 0) or 0)
            for item in families.values() if isinstance(item, dict)
        )
        passed = payload.get("passed_cases")
        scored = payload.get("scored_cases", case_count)
        result[variant] = {
            "passed_cases": passed,
            "scored_cases": scored,
            "case_accuracy": round(passed / scored, 4)
            if isinstance(passed, (int, float)) and isinstance(scored, (int, float)) and scored else None,
            "semantic_slot_precision": metrics.get("semantic_slot_precision"),
            "semantic_slot_recall": metrics.get("semantic_slot_recall"),
            "semantic_slot_f1": metrics.get("semantic_slot_f1"),
        }
    parser = report.get("parser") if isinstance(report.get("parser"), dict) else {}
    result["parser"] = {
        key: parser[key] for key in (
            "attempted_parses", "successful_parses", "failed_parses",
            "latency_p50_ms", "latency_p95_ms", "prompt_hint_bytes_mean",
        ) if key in parser
    }
    return result


def _fmt(value: Any, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}{suffix}" if isinstance(value, float) else f"{value}{suffix}"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Campaign Manager — informe de calidad", "",
        f"> **Estado global: {report['status'].upper()}**", "",
        f"- Commit: {report.get('commit') or 'desconocido'}",
        f"- Inicio: {report.get('started_at') or 'n/a'}",
        f"- Fin: {report.get('finished_at') or 'n/a'}",
        f"- Duración: {_fmt(report.get('duration_seconds'), ' s')}", "",
        "## 1. Resumen de ejecución", "",
        "| Fase | Estado | Duración | Código |",
        "|---|---:|---:|---:|",
    ]
    for stage in report["stages"]:
        lines.append(
            f"| {stage['name']} | {stage['status']} "
            f"| {_fmt(stage.get('duration_seconds'), ' s')} "
            f"| {_fmt(stage.get('exit_code'))} |"
        )
    local = report.get("local", {})
    tests = local.get("tests")
    if tests:
        lines.extend([
            "", "## 2. Calidad local / CI", "",
            "| Métrica | Resultado |", "|---|---:|",
            f"| Tests correctos | {tests.get('passed', 0)} |",
            f"| Fallos | {tests.get('failures', 0)} |",
            f"| Errores | {tests.get('errors', 0)} |",
            f"| Saltados | {tests.get('skipped', 0)} |",
        ])
    coverage = local.get("coverage")
    if coverage and coverage.get("available"):
        lines.extend([
            "", "### Cobertura Python", "",
            f"- Líneas: **{_fmt(coverage.get('line_percent'), '%')}**",
            f"- Branches: **{_fmt(coverage.get('branch_percent'), '%')}**",
            (f"- Combinada (gate 85%): **{_fmt(coverage.get('combined_percent'), '%')}** "
             f"({'PASS' if coverage.get('gate_passed') else 'FAIL'})"), "",
            "| Paquete | Líneas | Branches | Combinada |",
            "|---|---:|---:|---:|",
        ])
        for item in coverage.get("packages", []):
            lines.append(
                f"| {item['name']} | {item['lines_covered']}/{item['lines_valid']} "
                f"| {item['branches_covered']}/{item['branches_valid']} "
                f"| {_fmt(item['combined_percent'], '%')} |"
            )
    ollama = report.get("ollama", {})
    tests = ollama.get("tests")
    if tests:
        lines.extend([
            "", "## 3. Ollama / tests reales", "",
            "| Métrica | Resultado |", "|---|---:|",
            f"| Tests | {tests.get('tests', 0)} |",
            f"| Correctos | {tests.get('passed', 0)} |",
            f"| Fallos | {tests.get('failures', 0)} |",
            f"| Errores | {tests.get('errors', 0)} |",
            f"| Saltados | {tests.get('skipped', 0)} |",
            f"| Duración | {_fmt(tests.get('duration_seconds'), ' s')} |",
        ])
    if ollama.get("summary_file"):
        lines.append(f"\nInforme Ollama detallado: {ollama['summary_file']}")
    nlp = report.get("nlp", {})
    offline = nlp.get("offline")
    if offline and offline.get("available"):
        lines.extend([
            "", "## 4. NLP offline — Stanza", "",
            "| Métrica | Resultado |", "|---|---:|",
            f"| Escenarios | {offline.get('scenario_count', 'n/a')} |",
            f"| Parseos correctos | {offline.get('successful_parses', 'n/a')} |",
            f"| Parseos fallidos | {offline.get('failed_parses', 'n/a')} |",
            f"| Cobertura de parseo | {_fmt(offline.get('parse_coverage'))} |",
            f"| Modelo | {offline.get('model_package', 'n/a')} / {offline.get('library_version', 'n/a')} |",
            f"| Tamaño | {_fmt(offline.get('model_directory_megabytes'), ' MB')} |",
            (f"| Wall P50 / P95 | {_fmt(offline.get('wall_latency_p50_ms'), ' ms')} / "
             f"{_fmt(offline.get('wall_latency_p95_ms'), ' ms')} |"),
            (f"| CPU P50 / P95 | {_fmt(offline.get('cpu_latency_p50_ms'), ' ms')} / "
             f"{_fmt(offline.get('cpu_latency_p95_ms'), ' ms')} |"),
            "", "### Probes de negación y condicional", "",
            "| Señal | Variante | Muestras | Precisión | Recall | F1 |",
            "|---|---|---:|---:|---:|---:|",
        ])
        for cue in ("negation", "conditional"):
            for variant, label in (("lexical_baseline", "Léxico"), ("stanza", "Stanza")):
                values = offline["cue_metrics"][variant][cue]
                lines.append(
                    f"| {cue} | {label} | {values['samples']} "
                    f"| {_fmt(values['precision'])} | {_fmt(values['recall'])} "
                    f"| {_fmt(values['f1'])} |"
                )
    ab = nlp.get("ab")
    if ab and ab.get("available"):
        lines.extend([
            "", "## 5. A/B — Intent vs. Intent + Stanza", "",
            "| Variante | Correctos | Medidos | Exactitud | Slot P | Slot R | Slot F1 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ])
        for variant, label in (
            ("model_only", "Intent actual"),
            ("model_plus_stanza_hints", "Intent + Stanza"),
        ):
            values = ab.get(variant)
            if not values:
                continue
            lines.append(
                f"| {label} | {values.get('passed_cases', 'n/a')} "
                f"| {values.get('scored_cases', 'n/a')} "
                f"| {_fmt(values.get('case_accuracy'))} "
                f"| {_fmt(values.get('semantic_slot_precision'))} "
                f"| {_fmt(values.get('semantic_slot_recall'))} "
                f"| {_fmt(values.get('semantic_slot_f1'))} |"
            )
        ab_metadata = ab.get("metadata", {})
        if ab_metadata:
            lines.append(
                "\\nModelo A/B: "
                f"{ab_metadata.get('model', 'n/a')}; "
                f"llamadas: {ab_metadata.get('provider_calls', 'n/a')}; "
                f"duración: {_fmt(ab_metadata.get('elapsed_seconds'), ' s')}; "
                f"Ollama: {ab_metadata.get('ollama_version', 'n/a')}."
            )
        parser_metrics = ab.get("parser", {})
        if parser_metrics:
            lines.append(
                "\\nParser A/B: "
                f"{parser_metrics.get('successful_parses', 'n/a')}/"
                f"{parser_metrics.get('attempted_parses', 'n/a')} parseos; "
                f"P50/P95 {_fmt(parser_metrics.get('latency_p50_ms'), ' ms')} / "
                f"{_fmt(parser_metrics.get('latency_p95_ms'), ' ms')}; "
                f"hint medio {_fmt(parser_metrics.get('prompt_hint_bytes_mean'), ' bytes')}."
            )
    if report.get("artifacts"):
        lines.extend(["", "## 6. Artefactos", ""])
        lines.extend(f"- {item}" for item in report["artifacts"])
    lines.extend([
        "", "---", "",
        "Informe agregado. No contiene prompts, completions, utterances, lemas ni mensajes de error.",
        "",
    ])
    return "\n".join(lines)


def build_report(
    *,
    run_dir: Path,
    manifest_path: Path,
    commit: str,
    local_junit: Path | None = None,
    coverage_xml: Path | None = None,
    ollama_junit: Path | None = None,
    ollama_summary_path: Path | None = None,
    nlp_offline_path: Path | None = None,
    nlp_ab_junit: Path | None = None,
    nlp_ab_report_path: Path | None = None,
) -> dict[str, Any]:
    manifest = _read_json(manifest_path) or {}
    stages = manifest.get("stages", [])
    if not isinstance(stages, list):
        stages = []
    stages = [
        item for item in stages if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
    failed = any(item.get("status") == "failed" for item in stages)
    coverage = coverage_summary(coverage_xml)
    if coverage and coverage.get("available") and not coverage.get("gate_passed"):
        failed = True
    local_tests = junit_summary(local_junit)
    ollama_tests = junit_summary(ollama_junit)
    ab_tests = junit_summary(nlp_ab_junit)
    for item in (local_tests, ollama_tests, ab_tests):
        if item and item.get("available") and (item["failures"] or item["errors"]):
            failed = True
    offline = nlp_offline_summary(nlp_offline_path)
    ab = nlp_ab_summary(nlp_ab_report_path)
    ollama_existing = _read_json(ollama_summary_path)
    report = {
        "schema_version": 1,
        "status": "failed" if failed else "passed",
        "commit": commit,
        "started_at": manifest.get("started_at"),
        "finished_at": manifest.get("finished_at"),
        "duration_seconds": manifest.get("duration_seconds"),
        "stages": stages,
        "local": {"tests": local_tests, "coverage": coverage},
        "ollama": {
            "tests": ollama_tests,
            "summary_file": (
                str(ollama_summary_path.relative_to(run_dir))
                if ollama_summary_path and ollama_summary_path.is_file() else None
            ),
            "existing_summary": ollama_existing,
        },
        "nlp": {"offline": offline, "ab_tests": ab_tests, "ab": ab},
        "artifacts": [
            str(path.relative_to(run_dir))
            for path in sorted(run_dir.rglob("*"))
            if path.is_file() and path.name not in {"summary.json", "summary.md", "run-manifest.json"}
        ],
    }
    (run_dir / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "summary.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--local-junit", type=Path)
    parser.add_argument("--coverage-xml", type=Path)
    parser.add_argument("--ollama-junit", type=Path)
    parser.add_argument("--ollama-summary", type=Path)
    parser.add_argument("--nlp-offline", type=Path)
    parser.add_argument("--nlp-ab-junit", type=Path)
    parser.add_argument("--nlp-ab-report", type=Path)
    args = parser.parse_args()
    report = build_report(
        run_dir=args.run_dir, manifest_path=args.manifest, commit=args.commit,
        local_junit=args.local_junit, coverage_xml=args.coverage_xml,
        ollama_junit=args.ollama_junit, ollama_summary_path=args.ollama_summary,
        nlp_offline_path=args.nlp_offline, nlp_ab_junit=args.nlp_ab_junit,
        nlp_ab_report_path=args.nlp_ab_report,
    )
    print(
        f"Informe de calidad: {report['status'].upper()} | "
        f"{len(report['stages'])} fases | {report.get('duration_seconds') or 0:.1f}s"
    )
    print(f"Markdown: {args.run_dir / 'summary.md'}")
    print(f"JSON: {args.run_dir / 'summary.json'}")
    return 0  # Report generation succeeds independently of the tests it summarizes.


if __name__ == "__main__":
    raise SystemExit(main())
