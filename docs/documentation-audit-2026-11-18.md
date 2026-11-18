# Documentation freshness audit — 2026-11-18

**Repository:** `IvanVM04/Campaign-Manager`  
**Main baseline:** `4a3a2549bb0bb1bc38ec0e6f456ac6d5ccef24d1` (PR #257 merged).  
**Code baseline:** `f4fb3914ebab4579118863796e6f6d4b7183d0cf` (PR #255).  
**Inventory:** 118 tracked Markdown/text documentation files in the recursive repository tree at the baseline.

## 1. Objective and method

This audit checks whether repository documentation tells the same story as the current source and tests. It is not a general prose/style review.

Method:
1. Enumerated the recursive Git tree and inventoried 118 documentation files.
2. Read the root guidance, current documentation indexes, current product/quality docs, architecture contracts, migration catalogue, API routes/schemas, durable turn services/models, rules foundation and capability package guides.
3. Cross-checked high-risk claims against `migrations.py`, turn/API schemas, routers, service modules and tests.
4. Searched for superseded symbols/status claims, including `process_turn()`, `LegacySillyTavernTurnService`, in-memory pending-roll recovery claims, old PR #215–#219 priority claims and planned activity-history language.
5. Classified dated PR reports and point-in-time audits as historical evidence rather than silently rewriting their findings.

The 118-file number describes the discovered document inventory at the starting main baseline, not 118 files rewritten. The audit branch now contains 123 Markdown/text documents: the 118-file baseline plus five new current audit/navigation documents. Historical PR/audit snapshots are not individually re-certified as descriptions of current code; they are explicitly classified as dated evidence. Test-suite references in the new navigation were checked against the current Git tree (169 Python test files).

## 2. Executive result

The repository already had strong detail in many service guides and durable-adapter contracts, but the **navigation and current-source-of-truth layer had drifted**. The most serious defects were false “current” status and contradictory operational claims, not missing documentation volume.

The highest-risk inaccuracies identified:

- The active turn lifecycle document still called itself a proposed PR #28 architecture contract and listed manual-input continuation as future, despite durable clarification/manual-roll services and routes.
- The D&D 2014 rules foundation said manual rolls lived in memory, expired after 15 minutes and were lost on restart. Current durable turn records persist pending manual-roll challenge state.
- The LLM context-rendering page still described a removed legacy narrative-extraction renderer/path.
- The writer/lock audit still described the retired narrative-first `POST /integration/turn` as a live writer.
- The 12 Nov architecture map and 12 Nov audit still presented PRs #215–#219 as the current AI-understanding tranche.
- The 12 Nov engineering/readiness and 11 Nov CI/test documents were indexed as current even though more recent product/quality baselines existed.
- `legacy-sillytavern-turn-boundary.md` contradicts current code by saying the removed `process_turn()` path remains active.
- `observability-and-diagnostics.md` described PR #209 as a planned separate activity history; no separate player-facing activity timeline exists in the current code/docs/API.

## 3. Current canonical documents after this audit

| Purpose | Current source of truth |
|---|---|
| Intended product and owner-approved feature scope | [Product requirements v0.2](product/product-requirements-2026-11-18.md) |
| Current package ownership, paths and constraints | [Architecture map 2026-11-18](architecture/architecture-map-2026-11-18.md) |
| Current architecture assessment and product/code gaps | [Architecture audit 2026-11-18](architecture/architecture-audit-2026-11-18.md) |
| Cross-cutting code/test impact | [Change-impact map 2026-11-18](architecture/change-impact-map-2026-11-18.md) |
| Quality priorities and live acceptance order | [Quality roadmap 2026-11-18](quality/quality-roadmap-2026-11-18.md) |
| Test navigation | [Test-suite navigation 2026-11-18](quality/test-suite-navigation-2026-11-18.md) |
| Current durable turn state machine | [Turn-resolution lifecycle](architecture/turn-resolution-lifecycle.md) |
| API/adapter route behavior | [Turn pipeline contract](architecture/turn-pipeline-compatibility.md) and [SillyTavern durable adapter](architecture/sillytavern-durable-turn-adapter.md) |
| Migration history/schema version | [Migration catalogue](architecture/migration-catalog-2026-11-12.md), checked against `CURRENT_VERSION = 34` |

Use source code/tests if any document disagrees with implementation. Product requirements are not an implementation-status source.

## 4. Files corrected or refreshed

| File | Finding | Action |
|---|---|---|
| `README.md` | Singular-PC phrasing, outdated roadmap, vague UI and export scope; Ollama section omitted the intent role; integration endpoint code fence was unclosed. | Align product summary to v0.2; distinguish existing backend from future product capabilities; document four LLM roles and current routes; clarify `/export`; fix fenced examples. |
| `AGENTS.md` | Start-here links pointed at 12 Nov current maps and 11 Nov CI audit. | Repoint to current architecture, product, quality and test docs; keep historical audits as background only. |
| `docs/README.md` | Old indexes implied 12 Nov architecture/AI docs remained current. | Rebuild the source-of-truth hierarchy and classify old reports as historical. |
| `docs/architecture/README.md` | Duplicate/stale current links. | Repoint to 18 Nov audit/map/change-impact; add a historical section. |
| `docs/architecture/turn-resolution-lifecycle.md` | Proposed PR #28 status and old implementation narrative. | Rewrite to the implemented durable lifecycle and actual persisted challenge semantics. |
| `docs/architecture/dnd5e-2014-rules-engine.md` | In-memory manual-roll claim. | Correct to durable challenge persistence and current limitation boundaries. |
| `docs/architecture/llm-world-context-rendering-boundaries.md` | Retired legacy extraction path described as current. | Align with the live bounded proposal path. |
| `docs/architecture/writer-lock-cache-audit.md` | Retired route still in writer matrix. | Mark route removed and update the current route inventory. |
| `docs/architecture/observability-and-diagnostics.md` | Future activity history described as planned PR #209. | Clarify that technical logs and world events exist, but a separate activity timeline does not. |
| `docs/architecture/migration-catalog-2026-11-12.md` | Version accurate but verification date implicit. | Record the 18 Nov verification baseline and v34 explicitly. |
| `services/context/README.md` | Advanced discourse section stopped at PR #223. | Refresh current PR #246–#255 capability description and retain unresolved evaluation limits. |
| `services/turns/README.md` | Latest source changes not clearly distinguished from future uncertainty feature. | Add PR #255 current-state note and label configurable confidence threshold/checkpointing as future. |
| `services/campaign/README.md` | Runtime lifecycle checklist referred to three LLM roles after introduction of intent role. | Corrected to four roles. |
| `services/combat/README.md` | Expansion order linked to the 12 Nov engineering-readiness snapshot. | Pointed to current quality roadmap and architecture audit. |
| `services/world/README.md` | Application-level campaign/revision checks and architectural import-boundary tests remained unchecked. | Marked the implemented boundary/test coverage complete with exact source/test references. |
| `docs/quality/test-suite-navigation-2026-11-18.md` | Some proposed test paths did not exist in the current tree. | Cross-checked references against the 169-file Python test tree and replaced them with actual test modules/fixtures. |
| `docs/mvp-quickstart.md` | Existing demo path could be confused with full v0.2 campaign/product functionality. | Add explicit statement of the actual single-demo-character and current-client limits. |

New current map/audit/change-impact/test-navigation documents were added. The 12 Nov/11 Nov documents remain available with explicit supersession notices.

## 5. Classification of the 118-file inventory

### A. Current operational/source-of-truth documentation

These files should be maintained with code/contract changes:
- `README.md`, `AGENTS.md`, `docs/README.md`, `docs/architecture/README.md`.
- `docs/product/product-requirements-2026-11-18.md`, `docs/quality/quality-roadmap-2026-11-18.md`.
- The new 18 Nov architecture map, architecture audit, change-impact map and test-suite navigation.
- Current lifecycle/API/transaction/dependency contracts: `api-error-contract.md`, `package-dependency-matrix.md`, `turn-pipeline-compatibility.md`, `turn-resolution-lifecycle.md`, `sillytavern-adapter-boundary-2026-11-12.md`, `sillytavern-durable-turn-adapter.md`, `sqlite-transaction-ownership.md`, `world-applier-boundaries.md`, `llm-world-proposal-prompt-boundary.md`, `llm-world-context-rendering-boundaries.md`, `observability-and-diagnostics.md`, `writer-lock-cache-audit.md`.
- Current rules/operational guides and package contracts: `dnd5e-2014-rules-engine.md`, `campaign-clock.md`, combat/armor/weapon/effect guides, `mvp-quickstart.md`, `sillytavern-smoke-test.md`, `models/README.md`, all eight `services/*/README.md`.

### B. Historical point-in-time architecture snapshots

Preserve for rationale; do not treat old status/priority statements as current without revalidation:
- `docs/architecture/architecture-audit-2026-11-03.md`, `architecture-audit-2026-11-06.md`, `architecture-audit-2026-11-11.md`, `architecture-audit-2026-11-12.md` (all dated snapshots; 12 Nov has an explicit supersession notice).
- `current-architecture-2026-11-03.md`, `current-architecture-2026-11-05.md`, `comprehensive-architecture-audit-2026-11-05.md`, `audit-and-refactor-plan-2026-11-05.md`, `engineering-audit-2026-11-03.md`, `functional-audit-2026-11-03.md`, `architecture-decisions-2026-11-03.md`, `roadmap-2026-11-03.md`.
- `phase-0-closeout-2026-11-12.md`, `engineering-readiness-and-gameplay-roadmap-2026-11-12.md`, `legacy-cleanup-2026-11-06.md`, `legacy-extraction-boundary-audit-2026-11-12.md`, `legacy-prompt-decomposition-2026-11-12.md`, `legacy-retirement-2026-11-12.md`, `legacy-sillytavern-retirement-audit-2026-11-11.md`, `legacy-sillytavern-turn-boundary.md`, `domain-boundaries-2026-11-03.md`, and older durable-boundary proposals.
- `architecture-map-2026-11-12.md`, `module-catalog-2026-11-12.md` and `change-impact-map-2026-11-12.md` are now explicitly historical, with current replacements.

### C. Historical quality/AI evaluation snapshots

These retain corpus versions, observed failures, PR-level evidence and decisions. They should not be rewritten to imply that later PRs already existed:
- `ci-audit-2026-11-11.md`, `ci-quality-roadmap.md`, `pyright-baseline-2026-11-11.md`, `test-suite-audit-2026-11-11.md`, `test-suite-navigation-2026-11-12.md`.
- `ai-world-understanding-roadmap-2026-11-12.md`, `language-understanding-priority-2026-11-13.md`, `modular-language-understanding-pipeline-2026-11-14.md`, `semantic-understanding-next-phase-2026-11-13.md`, `language-understanding-audit-2026-11-14.md`, `language-understanding-architecture-audit-2026-11-16.md`, `advanced-discourse-understanding-2026-11-14.md`.
- Corpus/benchmark snapshots and PR execution records #226–#255, including predicate/discourse/semantic audits and holdout definitions.

### D. Domain and reference guides

The combat/armor/weapon/clock/effect/SRD attribution documents and package guides remain useful, but every mechanics or persistence change must update the matching domain guide and tests. These files are not evidence that the complete D&D 5e ruleset or product UI exists.

## 6. Important product-vs-implementation clarifications

The product v0.2 target includes:
- one or several PJ under player control;
- approved, auditable NPC delegation between player and DM;
- configurable uncertainty behavior and partial-turn checkpoint recovery;
- first-party interface with Simplified/Advanced modes and comprehensible field help;
- known-world compendium, entity links/previews and explicit context selection;
- NPC statistic visibility policy by entity/field;
- manual or backend dice policies with richer configuration;
- importable custom rules modules; Spanish/English first with future locales;
- complete campaign import/export.

Current code does **not** yet implement those full capabilities. The current implementation has one active character pointer, existing durable clarifications/corrections, automatic/manual turn dice mode, event-level visibility policy, world read endpoints and a player-safe `GET /export`. The new docs deliberately keep these states separate.

## 7. Remaining audit limitations and maintenance rules

- This pass is a documentation audit, not a re-run of the full test suite or an independent live Ollama/SillyTavern acceptance run. The source/test-file references and local Markdown links in the new navigation were checked against the current Git tree; no application code or migrations were changed.
- The dated PR/CI/AI reports preserve their original observations; use their banner and current pointers before reusing metrics.
- Where a page says “current”, include a verified source commit/date and point back to this index.
- Any PR that changes route, DTO, model, schema, provider contract, permissions, migration, rules or package ownership must update its owning guide and the change-impact map.
- New UI/product features must update both product requirements (target status) and implementation docs only when the code exists and tests verify it.
- Never mark an AI quality or live integration gate passed from deterministic CI alone.
