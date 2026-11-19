# PR #271 closure record

PR [#271](https://github.com/IvanVM04/Campaign-Manager/pull/271) was merged into main on 2026-11-19 as 9de344d4d36fdfc325c91f34075553d6076f2fc0. The PR head was a669d194462cced1ab2994a96ce60f25a4250b8.

## Validation

Final CI passed on that exact head:
- 2,204 deterministic tests passed.
- 22 real_llm tests deselected.
- 85.23% combined coverage (configured floor: 85%).
- Ruff, required Pyright package scope, repository-wide Pyright, JavaScript tests, CodeQL and CI summary all succeeded.

Evidence: [Tests #44559085820](https://github.com/IvanVM04/Campaign-Manager/actions/runs/44559085820) · [CodeQL #44559085674](https://github.com/IvanVM04/Campaign-Manager/actions/runs/44559085674).

Deterministic validation uses the commands from .github/workflows/tests.yml:

    python -m pytest -m "not real_llm" --cov --cov-report=term-missing --cov-report=xml
    ruff check .
    pyright models rules_engine bootstrap operations
    pyright --outputjson
    npm run test:js
    python -m coverage report

No Ollama live test or SillyTavern acceptance was run by CI.

## Delivered evaluator contract

- Text-free step-count gold covers 35 general language holdout scenarios.
- Text-free explicit frame/relation count gold covers all 20 semantic-frame holdout scenarios.
- Intent scoring enforces exact ordered step count and scores each gold-annotated step field at its expected index.
- Frame/relation scoring counts extras and duplicates as FP and omissions as FN.
- Missing gold annotations remain unmeasured; explicit zero-count gold is a negative control.
- Metric schema v1 reports case accuracy, TP/FP/FN, gold/prediction denominators, precision/recall/F1 and nearest-rank latency P50/P95.
- Provider/decoder failures remain scored misses.
- Live JSON reports reject arbitrary provider strings and do not persist utterance or completion text.

## Scope and holdout integrity

The PR changed evaluation tooling, tests, documentation and two text-free gold sidecars. The GitHub changed-file list did not include production runtime/prompt packages or the original held-out utterance corpus files. Original held-out utterance text and labels were not modified to make tests pass.

The 22 real_llm tests remained opt-in. No model-quality improvement is claimed by the deterministic CI result.

## Follow-on

PR #272 owns the optional NLP pilot. Stanza remains an opt-in experiment only; no production dependency or prompt integration is implied by the #271 merge.