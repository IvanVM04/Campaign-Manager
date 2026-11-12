# D&D Campaign Manager

Campaign Manager is evolving from a persistent campaign-state backend into an **AI Dungeon Master application for D&D 5e**.

The current implementation provides campaign state management, a REST API, structured world operations, memory/context retrieval, turn persistence and a SillyTavern integration. It is **not yet a complete D&D rules engine or a standalone AI Dungeon Master**. The product direction below describes the intended evolution; it must not be read as a claim that those future capabilities already exist.

> **Maintainers and coding agents:** start with [AGENTS.md](AGENTS.md) and the [documentation hub](docs/README.md). The current architecture, CI and test audits are indexed there; dated audits are historical snapshots.

## Product vision

The goal is to let a player describe what their character wants to do in natural language and have an AI Dungeon Master interpret the intent, consult the campaign, adjudicate the situation, apply the relevant game rules, update the world and narrate the outcome.

The application should own the campaign state and the turn-resolution workflow. The AI is responsible for interpretation, adjudication within the agreed rules, world direction and narration; deterministic application code is responsible for rule calculations, validation, permissions and persistence.

### Table authority

* **Player authority:** the player decides their player character's intentions, actions, dialogue and choices.
* **Dungeon Master authority:** the AI DM controls the world, environment, events, and NPCs that have not explicitly been delegated to a player.
* **Rules authority:** the rules engine resolves mechanical outcomes. The DM may adjudicate circumstances and call for appropriate checks, but generated narration must not override a mechanical result.
* **Application authority:** the application validates and persists state changes. An LLM must never write directly to the database or bypass domain validation.

A player may be allowed to portray or control selected NPCs, but this does not grant authority over the rest of the world or over facts those NPCs could not know.

### Ruleset scope and accuracy

The initial rules target is **D&D 5e, 2014–2015 rules baseline**. The 2014 rules are the first implementation target. The 2024 revision is explicitly out of initial scope and may be considered as a separate ruleset in a much later phase.

Rules must not be invented by the model. Mechanical behaviour must be implemented from verified rules references and represented in deterministic code wherever practical. Each implemented rule should have tests and a clear indication of its supported scope. If a rule is not implemented or its source is uncertain, the application must expose that limitation rather than silently improvising.

Ruleset-specific behaviour must be isolated so that a future 2024 implementation cannot accidentally mix with the 2014 rules.

### Intended turn-processing workflow

A player turn is intended to follow an explicit, inspectable pipeline:

1. Receive and record the player's natural-language input.
2. Build the relevant context: character, scene, world state, NPC knowledge, recent events and applicable rules.
3. Interpret the player's intent into structured candidate actions.
4. Check permissions and resolve ambiguities; ask the player for clarification when needed.
5. Have the AI DM adjudicate the circumstances and determine whether a check or game action is required.
6. Resolve mechanical outcomes through the deterministic rules engine.
7. Produce proposed world consequences and validate them against domain rules and campaign authority.
8. Persist the resolved turn and state changes atomically.
9. Generate the narrative response from the committed result.

A turn that needs clarification must not mutate the campaign. Narrative generation must not invent dice results or claim that an uncommitted state change occurred. Resolution and narration must be independently recoverable so that retries cannot apply damage, consume resources or create items twice.

Not every action requires a roll. The DM should use the rules and the fictional circumstances to distinguish routine actions from uncertain actions with meaningful consequences.

### Product scope

**Near-term product:** a complete campaign-management and AI-DM application, including campaign/session management, character sheets, world state, NPCs, rules adjudication, exploration, social interaction, combat and persistent campaign history.

**Not in the initial scope:** a virtual tabletop, tactical map editor, token movement, fog of war or real-time tabletop collaboration. These may be considered as a distant future extension after the core game experience is reliable.

The application is **single-player by design**: one person plays and manages their own campaigns, potentially maintaining several separate campaigns in the same installation. Multiplayer, shared tables, accounts and campaign membership are not part of the product scope. Remote access or hosted deployment is not part of the initial release and would require a separate security review.

### Architectural direction

The intended architecture is a **modular monolith** with clear domain boundaries and ports/adapters:

* a ruleset-independent application workflow;
* a versioned D&D 5e 2014 rules module;
* separate campaign, character, world, NPC, inventory, spellcasting, encounter and session domains;
* an AI DM orchestration layer with distinct interpretation, context, adjudication, consequence-planning and narration responsibilities;
* infrastructure adapters for persistence, LLM providers and external integrations.

The rules engine must be usable independently of an LLM, database, API or user interface. The AI may propose structured actions and consequences, but deterministic code validates and applies them.

This is the target architecture, not a description of completed modules. Existing components will be audited and migrated incrementally; the project should not be rewritten wholesale without a demonstrated need.

---

## Features

* **Persistent campaign state** backed by SQLite.
* **REST API** built with FastAPI.
* **SillyTavern integration** for processing generated narratives.
* **LLM-based structured proposals**, converting player intent into validated world-operation proposals.
* **Structured world operations** instead of allowing the LLM to directly modify the database.
* **In-memory `WorldState`** for efficient world manipulation.
* **Memory and context retrieval** for supplying relevant campaign information to the LLM.
* **Turn persistence** with operation and world-change metadata.
* **Turn versioning** using `external_turn_id` and `turn_version`.
* **Durable turn resolution**, committing consequences once before narration and keeping transcript versions separate.
* **Idempotency and conflict detection** for externally identified turns.
* **Historical turn-snapshot archive** preserving old JSON payloads after removal of the runtime snapshot/reconciliation path.
* **Database migrations** for controlled schema evolution.
* **Automated tests** covering services, repositories, API behaviour and turn reconciliation.

---

## Architecture

The current request path for SillyTavern is the durable adapter flow:

```text
SillyTavern extension
  -> POST /integration/turn/resolve
      -> DurableNativeTurnService
      -> TurnResolutionService.prepare_turn
          -> MechanicsAdjudicator
          -> deterministic supported d20 mechanics
          -> structured consequence proposal
      -> validate context revision + apply proposal
      -> atomic state + turn-resolution commit
  -> SillyTavern generates narrative from committed evidence
  -> POST /integration/turn/complete
      -> persist narrative version
```

The native `POST /turn` route uses the same durable coordinator and application resolution path, then narrates from the committed result. Manual rolls and clarifications pause and resume the same durable resolution. Regeneration/swipes create narrative versions without replaying world consequences. The narrative-first `POST /integration/turn` endpoint and its snapshot-reconciliation implementation have been removed; supported clients use the durable resolve/complete lifecycle.

The rules engine currently supports a deterministic subset of D&D 5e 2014: d20 checks/saves, initiative, attacks, damage, conditions, selected movement and weapon/encounter flows. It is not a complete character builder, spellcasting system or full 5e rules implementation.

For the current baseline, package ownership and ordered roadmap, start with the [architecture audit — 2026-11-12](docs/architecture/architecture-audit-2026-11-12.md), [architecture map](docs/architecture/architecture-map-2026-11-12.md), [shared-layer module catalogue](docs/architecture/module-catalog-2026-11-12.md) and [change-impact map](docs/architecture/change-impact-map-2026-11-12.md), all indexed from the [documentation hub](docs/README.md). The 2026-11-06, 2026-11-05 and 2026-11-03 audits are retained as dated snapshots. Active contracts remain documented in the [turn pipeline compatibility map](docs/architecture/turn-pipeline-compatibility.md), [writer/lock/cache audit](docs/architecture/writer-lock-cache-audit.md), and [SillyTavern smoke test](docs/sillytavern-smoke-test.md).

---


### Service package boundaries

The application services are organized into eight implemented capability packages rather than one flat service package. Their guides document current ownership, dependency rules and known follow-up work:

| Package guide | Responsibility |
|---|---|
| [campaign](services/campaign/README.md) | Campaign state, clock and runtime composition |
| [characters](services/characters/README.md) | Character creation and state use cases |
| [combat](services/combat/README.md) | Combat application workflows; mechanics stay in the rules engine |
| [context](services/context/README.md) | Context expansion, ranking, selection and rendering |
| [llm_world](services/llm_world/README.md) | World extraction prompts, parsing and proposal validation |
| [providers](services/providers/README.md) | LLM provider contracts, adapters and settings |
| [turns](services/turns/README.md) | Durable turn lifecycle, mechanics orchestration and narration |
| [world](services/world/README.md) | Validated world-operation application and serialization |

All eight capability packages contain implementation modules: campaign, characters, combat, context, llm_world, providers, turns and world. The external SillyTavern adapter is isolated under `integrations/adapters/silly_tavern`; it owns active context and transcript-state reads only. `bootstrap/campaign_runtime.py` owns composition. The narrative-first mutation route, legacy extraction API, snapshot repository and runtime snapshot column have been retired. Existing snapshot JSON is preserved in the inert `turn_snapshot_archive` table by migration 029. See the [current architecture audit](docs/architecture/architecture-audit-2026-11-12.md), [architecture map](docs/architecture/architecture-map-2026-11-12.md) and [module catalogue](docs/architecture/module-catalog-2026-11-12.md). New code should use canonical package paths. Do not restore flat service shims or retired mutation paths.

## Turn Processing

The current native and SillyTavern flows use the durable turn coordinator:

```text
Player intent
    |
    v
POST /turn  OR  POST /integration/turn/resolve
    |
    v
DurableNativeTurnService
    |
    +--> consistent context + campaign revision
    |
    +--> MechanicsAdjudicator
    |       -> deterministic supported d20 resolution
    |
    +--> structured consequence proposal
    |
    +--> validate + short BEGIN IMMEDIATE transaction
    |       -> apply world/character operations
    |       -> persist resolution, evidence and resulting revision
    |
    v
narration_pending
    |
    +--> native DMService OR SillyTavern generation
    |
    v
persist narrative / transcript version
    |
    v
completed
```

Clarifications and manual d20 rolls pause and resume the same durable resolution. The campaign state and resolution transition are committed atomically before narration. If narration fails, retrying the same request resumes narration without reapplying consequences.

The LLM proposes intent interpretation and structured world consequences from the player's input; deterministic application code validates operations, campaign scope and supported mechanics. Presentation prose is generated only after consequences are committed. The LLM is never allowed to write directly to SQLite. All supported clients use this single durable resolution contract.

---

## Turn Versioning & Regeneration

SillyTavern identifies a player action with a stable `external_turn_id`. The durable resolution belongs to that action, while generated assistant prose may have multiple versions.

- The first generation completes narrative version 1.
- A swipe/regeneration stores the next narrative version against the same committed resolution.
- A swipe does **not** restore the world snapshot, rerun mechanics or reapply consequences.
- Re-delivery of the same completed version is idempotent; conflicting content or invalid version sequencing is rejected.
- Clarification and manual-roll replies remain attached to the original external turn.

Regeneration creates narrative versions against the same committed resolution. It does not restore prior world state, rerun mechanics or reapply consequences. The old narrative-first endpoint has been removed. See the [turn pipeline contract](docs/architecture/turn-pipeline-compatibility.md) and [durable SillyTavern adapter contract](docs/architecture/sillytavern-durable-turn-adapter.md).

---

## Historical snapshot archive

Migration 029 copies every non-null JSON value from the former `turns.snapshot`
column into `turn_snapshot_archive` and removes the column from the active
`turns` table. The archive is intentionally inert: runtime code has no reader,
writer or restore operation for these payloads. Existing campaign history is
preserved without keeping the old regeneration architecture alive.

## Database

The project uses **SQLite** as its persistent storage layer.

The database is created automatically under:

```text
data/campaign.db
```

Schema changes are managed through application migrations rather than relying on manual database modifications.

This keeps the project local and lightweight while still providing explicit schema evolution.

---

## API

The application exposes a REST API through FastAPI capability routers under `api/routers/`. Every campaign-scoped endpoint requires the `X-Campaign-Id` request header. The `/`, `/health`, `/ready`, API documentation, CORS preflight and campaign listing/creation endpoints are exempt.

Example:

```http
X-Campaign-Id: 2
```

The selected campaign is resolved to a dedicated `CampaignRuntime`, which owns its in-memory world, services and turn-execution lock. Requests without the header are rejected; the API never silently falls back to campaign 1. The SillyTavern extension exposes a **Campaign ID** setting and sends the header with every backend request.

**Local security boundary:** `X-Campaign-Id` selects one of the local user's campaigns; it is not an authentication credential. This is intentional for the single-player, local-first application. The server is configured to bind to `127.0.0.1`, so it is not exposed to other machines by the documented default commands. Do not change the bind address to `0.0.0.0` or expose the API through a reverse proxy/tunnel without adding an explicit authentication mechanism and reviewing campaign access. Remote access is a separate future scope.

### Basic

```text
GET /
GET /health
GET /ready
```

### Campaign

```text
GET   /campaigns
POST  /campaigns
PATCH /campaign
PATCH /campaign/session
GET   /campaign/state
PATCH /campaign/active-character
```

### Turns

```text
POST /turn
POST /turn/roll
POST /turn/clarification
GET  /turns
```

### Dice tray

```text
POST /dice/roll
```

The standalone dice tray accepts `count`, `sides` and `modifier`. A single d20 also supports `advantage` or `disadvantage`. It returns each die result and the final total without creating a turn or changing campaign state.

### Memory

```text
GET /memory/search
GET /memory/context
```

### SillyTavern integration

```text
POST /integration/context
POST /integration/turn/resolve
POST /integration/turn/roll
POST /integration/turn/clarification
GET  /integration/turn/{external_turn_id}
GET  /integration/turn/{external_turn_id}/clarification
GET  /integration/turn/{external_turn_id}/manual-roll
POST /integration/turn/complete


### World

```text
GET /world
```

### Export

```text
GET /export
```

Interactive API documentation is available through FastAPI's generated documentation:

```text
http://127.0.0.1:8765/docs
```

---

## Requirements

* Python 3.12+
* Ollama
* A compatible local LLM model
* SillyTavern (for the integration workflow)

The backend itself uses:

* FastAPI
* Uvicorn
* SQLite
* Pydantic

Development and testing tools include:

* pytest (pinned in the `test` dependency group)
* Ruff (pinned in the `lint` dependency group)
* Pyright (pinned in the `typing` dependency group)
* httpx2 (pinned in the `test` dependency group)

---

## Installation

Clone the repository:

```bash
git clone https://github.com/IvanVM04/Campaign-Manager.git
cd Campaign-Manager
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

Install the runtime dependencies:

```bash
pip install -r requirements.txt
```

Install the development/test tools:

```bash
pip install --group test --group lint --group typing
```

The database will be initialized automatically when the application starts.

---

## Running

### Windows

The repository includes:

```text
start.bat
```

Alternatively, start the server manually:

```bash
.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8765
```

The API will be available at:

```text
http://127.0.0.1:8765
```

Liveness check (HTTP process):

```text
http://127.0.0.1:8765/health
```

Readiness check (SQLite reachable):

```text
http://127.0.0.1:8765/ready
```

Expected readiness response:

```json
{
  "ok": true,
  "database": "ready"
}
```

Interactive API documentation:

```text
http://127.0.0.1:8765/docs
```

---

## Ollama

The application uses `OllamaProvider` as its local LLM adapter. Ollama must be running and the configured models must be available.

Provider settings are read from environment variables when the backend starts. Defaults preserve the existing setup: `http://localhost:11434`, model `gemma4:26b` for all three responsibilities, and a 120-second timeout per request. Structured extraction also has conservative context, total-prompt, output-size and repair-request budgets.

| Variable | Default | Purpose |
|---|---|---|
| `CAMPAIGN_MANAGER_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama HTTP base URL |
| `CAMPAIGN_MANAGER_LLM_NARRATIVE_MODEL` | `gemma4:26b` | Model used for DM narration |
| `CAMPAIGN_MANAGER_LLM_EXTRACTION_MODEL` | `gemma4:26b` | Model used to propose structured world operations |
| `CAMPAIGN_MANAGER_LLM_MECHANICS_MODEL` | `gemma4:26b` | Model used for mechanics adjudication |
| `CAMPAIGN_MANAGER_LLM_NARRATIVE_TIMEOUT_SECONDS` | `120` | Narration request timeout |
| `CAMPAIGN_MANAGER_LLM_EXTRACTION_TIMEOUT_SECONDS` | `120` | Extraction request timeout |
| `CAMPAIGN_MANAGER_LLM_MECHANICS_TIMEOUT_SECONDS` | `120` | Mechanics request timeout |
| `CAMPAIGN_MANAGER_LLM_EXTRACTION_PROMPT_MAX_TOKENS` | `8192` | Upper bound for the complete structured proposal prompt |
| `CAMPAIGN_MANAGER_LLM_EXTRACTION_CONTEXT_MAX_TOKENS` | `4096` | Upper bound for selected world context; cannot exceed the complete prompt budget |
| `CAMPAIGN_MANAGER_LLM_EXTRACTION_MAX_RESPONSE_CHARS` | `16000` | Maximum provider response size for extraction/proposal output |
| `CAMPAIGN_MANAGER_LLM_EXTRACTION_REPAIR_MAX_TOKENS` | `2048` | Independent upper bound for the single proposal repair request |

Example (PowerShell):

```powershell
$env:CAMPAIGN_MANAGER_LLM_NARRATIVE_MODEL = "gemma4:26b"
$env:CAMPAIGN_MANAGER_LLM_EXTRACTION_MODEL = "qwen2.5:14b"
$env:CAMPAIGN_MANAGER_LLM_MECHANICS_MODEL = "qwen2.5:14b"
$env:CAMPAIGN_MANAGER_LLM_EXTRACTION_TIMEOUT_SECONDS = "90"
uvicorn app:app --reload
```

The settings are validated at startup. Invalid URLs, empty model names, non-positive/non-finite timeouts or invalid extraction budgets prevent the application from starting rather than failing later during a turn. All roles may use the same model; separate models and timeouts are optional tuning points. The token limits use a pessimistic one-UTF-8-byte-per-token upper bound because the current provider port does not expose an exact tokenizer count. The structured proposal path uses separate context, complete-prompt, response and one-repair budgets. Restart the backend after changing environment variables.

---

## SillyTavern Integration

The current extension resolves and commits consequences before it asks SillyTavern to generate prose. It then persists the narrative against the same external turn identity. Campaign Manager remains the authority for persistent campaign state and supported mechanics; SillyTavern remains the narrative interface.

See [the smoke-test checklist](docs/sillytavern-smoke-test.md) for manual acceptance scenarios covering duplicate delivery, swipes, clarification, manual rolls, restart recovery and persistent world continuity. Use a disposable campaign for this test.
---

## Testing

The project uses `pytest`.

### Standard test suite

The default CI test command excludes tests that require a running local LLM:

```bash
python -m pytest -m "not real_llm"
```

This is the deterministic suite used for continuous integration.

### Real LLM tests

Tests marked `real_llm` require Ollama to be running with a compatible model:

```bash
python -m pytest -m real_llm
```

### Full local suite

When Ollama is configured and available, the complete suite can be run with:

```bash
python -m pytest
```

The test suite covers the main application layers, including:

* repositories;
* services;
* world operations;
* API endpoints;
* persistence;
* turn processing;
* SillyTavern integration;
* restart/persistence behaviour;
* turn versioning;
* narrative versioning without replaying world consequences;
* failed regeneration rollback;
* idempotency and conflict handling;
* context before and after a persisted turn.

The goal is not only to test individual functions, but also to verify that persistent campaign state remains consistent across different turn versions and application restarts.

---

## Continuous Integration

GitHub Actions runs checks on pushes and pull requests targeting `main`.

The current workflows provide:
- deterministic Python tests with coverage (excluding `real_llm`);
- Ruff lint;
- required-scope Pyright for `models`, `rules_engine`, `bootstrap` and `operations`;
- blocking repository-wide Pyright (the current baseline is zero diagnostics);
- JavaScript tests on Node 20;
- CodeQL analysis for Python and JavaScript/TypeScript;
- weekly Dependabot updates for GitHub Actions, pip and npm.

The real-LLM tests are intentionally excluded from deterministic CI because they require a running Ollama service and compatible model. CodeQL runs as a separate workflow.

**Merge protection:** the active default-branch ruleset requires `CI summary`, `Analyze (python)` and `Analyze (javascript-typescript)`. The aggregate check blocks merges when Ruff, deterministic tests, scoped/repository-wide Pyright or JavaScript tests fail. Inspect the complete PR checks before merging. See the [CI audit](docs/quality/ci-audit-2026-11-11.md).

---

## Engineering documentation

- [Documentation hub for maintainers and agents](docs/README.md)
- [Current architecture and modularity audit](docs/architecture/architecture-audit-2026-11-12.md)
- [Architecture map](docs/architecture/architecture-map-2026-11-12.md)
- [Shared-layer module catalogue](docs/architecture/module-catalog-2026-11-12.md)
- [Cross-layer change-impact map](docs/architecture/change-impact-map-2026-11-12.md)
- [Capability dependency matrix](docs/architecture/package-dependency-matrix.md)
- [CI and quality-gate audit](docs/quality/ci-audit-2026-11-11.md)
- [Test-suite audit](docs/quality/test-suite-audit-2026-11-11.md)
- [CI quality roadmap](docs/quality/ci-quality-roadmap.md)
- [Durable turn lifecycle](docs/architecture/turn-resolution-lifecycle.md)
- [Writer, lock and cache-coherence audit](docs/architecture/writer-lock-cache-audit.md)

Older architecture documents remain available from the [architecture index](docs/architecture/README.md) as dated historical snapshots.

## Design Decisions

### Structured operations instead of direct LLM database access

The LLM does not directly modify SQLite.

Instead:

```text
LLM
 ↓
Extracted operation
 ↓
Parser
 ↓
Domain validation
 ↓
WorldService
 ↓
SQLite
```

This creates a controlled boundary between probabilistic LLM output and deterministic application state.

---

### SQLite instead of a server database

SQLite keeps the project:

* local;
* portable;
* easy to install;
* suitable for a single-user campaign manager.

A server database can be introduced later if the project evolves toward a multi-user or hosted architecture.

---

### In-memory WorldState + persistent SQLite

The application keeps the active world in memory for domain operations while using SQLite as persistent storage.

This gives the domain layer a convenient object-oriented representation of the world without making the LLM or business logic dependent on raw SQL queries.

---

### Durable turn identity and versioning

`external_turn_id` identifies one logical player action across retries,
clarifications and narrative regenerations. `turn_version` and `status`
distinguish active and superseded narrative versions. The committed durable
resolution is authoritative; narrative versions never restore a previous
world snapshot or replay consequences.

## Historical snapshot retention

Old regeneration snapshots are retained only as archival JSON in
`turn_snapshot_archive`. They are not part of the runtime model and are never
read by the application.

## Runtime model

Campaign Manager currently assumes a single Python process.

Each campaign runtime keeps its own `WorldState` in memory and uses a
campaign-local `TurnExecutionLock` to serialize turn execution. Runtime
instances are cached by campaign ID within the single Python process.

For this reason, the application must currently be run with a single
Uvicorn worker.

Do not start the application with multiple workers, for example:

    uvicorn app:app --workers 4

Multiple Python processes would have independent in-memory world states
and independent execution locks. SQLite would still serialize database
writes, but it would not synchronize those in-memory states.

The supported runtime is therefore:

    uvicorn app:app --host 127.0.0.1 --port 8765

or the provided `start.bat`.

A future multi-process deployment would require an explicit shared-state
or distributed-locking strategy.

## Project Structure

```text
Campaign-Manager/
│
├── app.py
├── database.py
├── migrations.py
├── requirements.txt
├── pyproject.toml
├── start.bat
│
├── models/
│   └── Domain and API models
├── operations/
│   └── Structured world operations
├── repositories/
│   └── SQLite persistence layer
├── services/
│   ├── campaign / characters / combat / context
│   ├── llm_world / providers / turns / world
├── integrations/
│   └── adapters/silly_tavern
├── tests/
│   └── Automated test suite
└── data/
    └── campaign.db
```

---

## Current Status — Checkpoint

The current checkpoint has the core state-management and integration flow covered by automated tests.

Validated areas include:

* persistent campaign state;
* structured world operations;
* structured LLM proposals from player intent;
* context and memory retrieval;
* SQLite persistence;
* REST API;
* SillyTavern integration;
* turn versioning;
* idempotency and conflict detection;
* narrative-version idempotency and conflict detection;
* recoverable narration failure without replaying consequences;
* persistence across a simulated application restart;
* end-to-end `context → turn → context` behaviour;
* automated CI testing and Ruff linting.

The current implementation is focused on **reliable campaign state management and integration correctness**. The AI Dungeon Master workflow, comprehensive D&D 5e 2014 rules engine, full character progression and combat system described in the product vision are future development work, not completed features.

This checkpoint is intended as a stable baseline for the next development pass. If subsequent changes introduce regressions, the state-management, persistence and integration layers can be re-audited from this baseline.

---

## Roadmap

The roadmap follows the product vision and prioritizes correctness before breadth:

1. **Architecture and reliability:** audit the existing code, fix transaction/state consistency, define domain boundaries, introduce explicit transaction management and test critical failure paths.
2. **AI DM turn pipeline:** define typed turn states and contracts for intent interpretation, context planning, adjudication, consequence validation, persistence and narration. Preserve the existing SillyTavern integration during migration.
3. **D&D 5e 2014 rules foundation:** implement and test dice, ability modifiers, proficiency, skills, saving throws and advantage/disadvantage against verified rules references.
4. **Playable character model:** build character creation, class/background/species data, equipment, features and level progression in controlled increments.
5. **Exploration and social play:** scenes, NPCs, knowledge boundaries, checks, dialogue and persistent consequences.
6. **Combat and spellcasting:** encounters, initiative, actions, attacks, damage, conditions, rests and spellcasting.
7. **Standalone application experience:** web interface for campaigns, sessions, character sheets, world management and the AI DM.
8. **Distant future:** virtual tabletop capabilities and, separately, a D&D 5e 2024 ruleset.

The roadmap is a target, not a claim that these capabilities are already implemented. Each rules feature must have an explicit supported-scope statement and deterministic tests.

---

## Why This Project?

Although the project is built around a D&D use case, its underlying problems are broader:

* integrating probabilistic LLM output with deterministic application state;
* designing persistent domain models;
* maintaining consistency across external clients;
* handling retries and idempotency;
* reconciling different versions of the same operation;
* separating domain logic from infrastructure;
* testing stateful workflows.

The project therefore serves as a practical exploration of **LLM application architecture, state management, persistence and API design**.

---

## License

This project is currently provided as-is for personal and educational use.
