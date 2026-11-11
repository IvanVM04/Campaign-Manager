# Pyright baseline — 2026-11-11

## Scope and provenance

This report records the first informational Pyright run introduced by PR #163, using Pyright 1.1.414 and `pyrightconfig.json` at the merged commit. The analysis includes first-party application code in `api`, `bootstrap`, `models`, `operations`, `repositories`, `rules_engine`, `services`, plus `app.py`, `database.py` and `migrations.py`. Tests and scripts are excluded.

The JSON report was produced by workflow run `43042317771` and retained as the `pyright-baseline` artifact. It is a point-in-time baseline, not a statement that every diagnostic is a runtime defect.

## Baseline summary

| Measure | Result |
|---|---:|
| Diagnostics | 98 |
| Errors | 98 |
| Warnings / information | 0 |
| Files with diagnostics | 27 |
| Scope | First-party application code |

### By package

| Package | Diagnostics |
|---|---:|
| `services/` | 65 |
| `repositories/` | 16 |
| `api/` | 10 |
| `models/` | 5 |
| `rules_engine/` | 2 |

There were no diagnostics in `bootstrap/`, `operations/`, or the three included root-level modules in this run. This makes them potential candidates for a future clean-scope gate, subject to verifying the scope remains complete and stable.

### By diagnostic rule

| Rule | Count | Initial interpretation to verify |
|---|---:|---|
| `reportArgumentType` | 63 | Incompatible argument types, including optional values and collection/protocol mismatches |
| `reportAttributeAccessIssue` | 10 | Attribute not present on the inferred type; inspect annotations and third-party stubs |
| `reportOptionalMemberAccess` | 10 | Member access without sufficient `None` narrowing |
| `reportReturnType` | 8 | Return value does not satisfy the declared return type, often due to optional values or incomplete branches |
| `reportOptionalSubscript` | 4 | Subscript applied to a value Pyright considers optional |
| `reportAssignmentType` | 2 | Assigned literal/value does not match the declared type |
| `reportOperatorIssue` | 1 | Operand types do not satisfy the operation |

These categories are triage hints, not automatic fixes. In particular, do not silence optional-value diagnostics with casts or assertions until the domain invariant and runtime behavior have been checked.

### Largest file hotspots

| File | Diagnostics |
|---|---:|
| `services/turns/durable_native_turn_service.py` | 18 |
| `services/world/world_resource_applier.py` | 12 |
| `services/world/world_item_applier.py` | 11 |
| `services/combat/combat_attack_service.py` | 6 |
| `api/errors.py` | 5 |
| `repositories/turn_resolution_repository.py` | 5 |
| `repositories/world_snapshot_repository.py` | 5 |

The remaining 20 affected files contain one to four diagnostics each. The hotspots should be reviewed by contract and behavior, not bulk-cast or suppressed to reduce the count.

## Triage plan

1. Review `reportOptionalMemberAccess`, `reportOptionalSubscript` and optional-related `reportArgumentType` / `reportReturnType` findings first. Confirm whether each is a real missing guard, an invariant not expressed in types, or a stub limitation.
2. Review service and repository argument mismatches at their boundaries. Prefer accurate domain types and explicit normalization over widening APIs to `Any`.
3. Review the `api/errors.py` FastAPI typing findings against the installed FastAPI version and its stubs before changing the error-handler contract.
4. Keep `legacy_silly_tavern_turn_service.py` and `world_snapshot_repository.py` findings visible until the legacy route retirement decision is made; do not use type cleanup as a reason to delete compatibility behavior.
5. After fixing the two current `rules_engine/` findings and confirming the package has no diagnostics, consider a blocking Pyright job scoped to `rules_engine/`. Expand the gate only when another package is clean and its public contracts are stable.

## Guardrails

- Do not add global ignores or blanket `Any` annotations to make the report green.
- Do not use `cast`, `# type: ignore`, or `assert value is not None` without documenting the invariant at the boundary.
- Type-only changes must preserve runtime behavior and be covered by the existing deterministic tests.
- Keep the repository-wide Pyright job informational until the baseline has been reduced and reviewed package by package.
- Re-run the report after tool, dependency or configuration changes; compare by package, rule and file rather than only the total count.
