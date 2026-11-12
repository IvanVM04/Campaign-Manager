# Context scale and proposal-quality probes — 2026-11-12

**Scope:** deterministic tests for the active structured proposal path.  
**Baseline:** post-PR #206; no production behavior changes in this probe set.

## Goals

Exercise campaign-context selection with representative larger synthetic graphs
without relying on wall-clock timing thresholds or a live model. The tests
protect selection stability, budget behavior, mandatory facts, dependencies,
detachment and the proposal parser/repair contract.

## Synthetic campaign shape

`tests/context_scale_test_support.py` builds deterministic worlds with:

- 600–900 searchable NPC entities plus a mandatory player and location;
- ownership and dependency records for item instances and resource balances;
- campaign relations and public/secret events;
- optional reverse insertion order to detect hidden dependence on dict order.

The builder intentionally uses stable domain IDs and fixed text. It does not
create SQLite fixtures or call external providers.

## Probe matrix

| Test module | Probe | Contract |
|---|---|---|
| `tests/test_context_scale_probes.py` | Large campaign (900 NPCs) | Candidate/selected/available diagnostics, optional-record exclusion, mandatory entity retention, related item/resource resolution, public-event retention, secret-event exclusion and canonical-world immutability. |
| Same | 700-NPC insertion-order comparison | The same query and budget produce the same selected IDs and diagnostics when source dictionaries are inserted in reverse order. |
| Same | 600-NPC budget comparison | A larger budget admits more optional records while retaining all mandatory facts and staying within each configured budget. |
| `tests/test_proposal_scale_quality.py` | 750-NPC structured proposal | The selected projection is rendered within the prompt budget and parsed into a typed `CreateEventOperation`; secret event text is absent. |
| Same | Invalid proposal on a large campaign | Exactly one compact repair is performed; it does not resend the full world context and respects the repair byte/token upper bound. |

## Interpretation

These tests are regression/scale-shape probes, not a performance benchmark.
They deliberately avoid assertions on elapsed milliseconds, which would be
machine-dependent and flaky in shared CI. They use the current conservative
UTF-8-byte upper bound and do not claim exact model-token counts.

A green deterministic run validates retrieval/selection/prompt contracts with
the fake provider. It does not validate Ollama model quality, local latency,
GPU/CPU memory pressure or the SillyTavern extension. Those remain in the
separate manual acceptance checklist and are deferred until the full local
environment is mounted.

## Follow-up decision

Do not add semantic/vector retrieval, a cache, database index or a different
ranking algorithm based only on synthetic size. First capture a real campaign
fixture or a reproducible live-model failure, then compare the current
deterministic baseline against the specific workload.
