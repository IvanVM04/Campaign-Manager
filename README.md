# D&D Campaign Manager

Campaign Manager is evolving from a persistent campaign-state backend into an **AI Dungeon Master application for D&D 5e**.

The current implementation provides campaign state management, a REST API, structured world operations, memory/context retrieval, turn persistence and a SillyTavern integration. It is **not yet a complete D&D rules engine or a standalone AI Dungeon Master**. The product direction below describes the intended evolution; it must not be read as a claim that those future capabilities already exist.

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
* **LLM-based world extraction**, converting narrative text into structured operations.
* **Structured world operations** instead of allowing the LLM to directly modify the database.
* **In-memory `WorldState`** for efficient world manipulation.
* **Memory and context retrieval** for supplying relevant campaign information to the LLM.
* **Turn persistence** with operation and world-change metadata.
* **Turn versioning** using `external_turn_id` and `turn_version`.
* **Swipe / regeneration reconciliation**, restoring the previous world snapshot before applying a regenerated turn.
* **Idempotency and conflict detection** for externally identified turns.
* **World snapshots** used to reconcile different versions of the same turn.
* **Database migrations** for controlled schema evolution.
* **Automated tests** covering services, repositories, API behaviour and turn reconciliation.

---

## Architecture

The application is organized around a layered architecture that separates HTTP handling, domain logic, persistence and LLM interaction.

```text
                         ┌─────────────────┐
                         │   SillyTavern   │
                         │ Narrative / UI  │
                         └────────┬────────┘
                                  │
                    player_input + narrative
                                  │
                                  ▼
                    ┌───────────────────────┐
                    │        FastAPI        │
                    │      REST API         │
                    └───────────┬───────────┘
                                │
                                ▼
              ┌────────────────────────────────┐
              │ SillyTavernIntegrationService  │
              └───────────────┬────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
          ┌─────────────────┐   ┌──────────────────┐
          │ ContextBuilder  │   │ LLMWorldExtractor│
          │ Memory Search   │   │ Operation Parser │
          └─────────────────┘   └────────┬─────────┘
                                         │
                                         ▼
                               ┌──────────────────┐
                               │   WorldService   │
                               │  WorldApplier    │
                               └────────┬─────────┘
                                        │
                                        ▼
                                  ┌───────────┐
                                  │  SQLite   │
                                  │ Persistence│
                                  └───────────┘
```

### Main components

#### `WorldService`

Owns the current in-memory `WorldState` and coordinates the application of structured operations.

The service works against a working copy of the world and persists successful changes to SQLite.

#### `TurnResolutionService`

Coordinates the domain-level resolution of a turn without coupling the core turn flow directly to the HTTP layer.

Its responsibilities include coordinating:

* narrative generation;
* context;
* world extraction;
* operation application;
* turn resolution results.

#### `SillyTavernIntegrationService`

Acts as the integration boundary between SillyTavern and the campaign backend.

It handles:

* incoming player input;
* generated narrative;
* persistent context;
* world extraction;
* turn persistence;
* external turn identifiers;
* turn versions;
* regeneration reconciliation.

#### `LLMWorldExtractor`

Uses an LLM to identify persistent world changes from narrative text.

Instead of letting generated text directly manipulate the database, the LLM produces structured operations that are subsequently parsed, validated and applied by the application.

#### `OperationParser`

Converts the extracted representation into domain operations such as creating or modifying world entities and item instances.

#### `MemorySearchService`

Provides retrieval over the current world state and builds structured representations that can be used as persistent campaign memory.

#### Repositories

Persistence is separated from the domain services through repository classes.

Examples include:

* `CampaignRepository`
* `CharacterRepository`
* `EntityRepository`
* `TurnRepository`
* `WorldSnapshotRepository`

---

## Turn Processing

A normal SillyTavern turn follows this general flow:

```text
Player action
     │
     ▼
SillyTavern generates narrative
     │
     ▼
POST /integration/turn
     │
     ▼
LLMWorldExtractor
     │
     ▼
Structured operations
     │
     ▼
Operation validation
     │
     ▼
WorldService
     │
     ▼
SQLite persistence
     │
     ▼
TurnRecord
```

The narrative itself is not treated as the source of truth for persistent state.

Instead:

```text
Narrative
    ↓
LLM extraction
    ↓
Structured operations
    ↓
Domain validation
    ↓
WorldState
    ↓
SQLite
```

This makes the LLM an interpreter of the narrative rather than the component directly responsible for database mutations.

---

## Turn Versioning & Regeneration

One of the main consistency problems when integrating with SillyTavern is **response regeneration / swiping**.

For example:

```text
Turn 42
  Version 1
      │
      ├── Player: "I open the chest."
      │
      └── Narrative: "You find an ancient sword."
                │
                ▼
          World changes
          Sword created


User regenerates response


Turn 42
  Version 2
      │
      ├── Same player action
      │
      └── Different narrative
                │
                ▼
          Restore snapshot
                │
                ▼
          Apply version 2
```

Each externally identified turn can therefore have multiple versions:

```text
external_turn_id = "turn-42"

version 1 → superseded
version 2 → superseded
version 3 → active
```

Before applying a new version, the previous active version's world snapshot is restored.

This prevents regenerated narratives from accumulating mutually incompatible world changes.

### Idempotency

If the same `external_turn_id` and version are received again with identical content, the persisted result can be reused instead of applying the turn twice.

If the same identifier/version is received with different content, the integration reports a conflict.

Older versions are also rejected once a newer active version exists.

This provides a clear consistency model for external turn processing.

---

## World Snapshots

Snapshots are used to reconcile different versions of a turn.

A snapshot contains the persistent world tables required to restore campaign state, including:

* entities;
* items;
* item instances;
* resources;
* resource balances;
* relations;
* world events;
* character states.

The snapshot mechanism allows the application to move from:

```text
World before Turn 42
        ↓
Turn 42 / Version 1
        ↓
World after Version 1
```

back to:

```text
World before Turn 42
```

and then apply:

```text
Turn 42 / Version 2
```

This is particularly useful for LLM-driven interfaces where users can regenerate previously generated responses.

---

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

The application exposes a REST API through FastAPI. Every campaign-scoped endpoint requires the `X-Campaign-Id` request header. The `/`, `/health`, API documentation, CORS preflight and campaign listing/creation endpoints are exempt.

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
GET  /turns
```

### Memory

```text
GET /memory/search
GET /memory/context
```

### SillyTavern integration

```text
POST /integration/context
POST /integration/turn
```

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

* pytest
* Ruff
* httpx

---

## Installation

Clone the repository:

```bash
git clone https://github.com/ivin04/Campaign-Manager.git
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
pip install pytest "httpx2>=2.5" ruff
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

The application uses an `OllamaProvider` as the local LLM provider.

Ollama must therefore be running locally with a compatible model available.

The exact model is intentionally not hard-coded into the project documentation so that the backend can be used with different local models depending on available hardware and desired performance.

---

## SillyTavern Integration

The intended workflow is:

```text
SillyTavern
     │
     │ Generate narrative
     ▼
Campaign Manager
     │
     ├── Retrieve persistent context
     │
     ├── Extract world changes
     │
     ├── Validate operations
     │
     ├── Apply changes
     │
     └── Persist turn
     ▼
SQLite
```

Campaign Manager does not replace SillyTavern as the narrative interface.

Instead, it acts as a persistent campaign-state backend.

This separation allows the narrative layer and the world-state layer to evolve independently.

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
* regeneration / snapshot reconciliation;
* failed regeneration rollback;
* idempotency and conflict handling;
* context before and after a persisted turn.

The goal is not only to test individual functions, but also to verify that persistent campaign state remains consistent across different turn versions and application restarts.

---

## Continuous Integration

GitHub Actions runs the automated checks on pushes and pull requests targeting `main`.

The CI pipeline currently performs three jobs:

```text
pytest (excluding real_llm tests)
        +
Ruff linting
        +
JavaScript tests (Node 20)
```

The real LLM tests are intentionally excluded from CI because they require a locally running Ollama service and model.

Each job reports its own status in the pull request; wait for all three jobs to finish before treating the CI run as complete.

---

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

### Snapshots for turn reconciliation

Regenerating an LLM response can invalidate state changes produced by the previous response.

Snapshots provide an explicit mechanism to restore the state associated with the previous version before applying the new one.

This makes turn regeneration a state-reconciliation problem rather than simply inserting another turn into the database.

---

### External turn identifiers

SillyTavern and similar clients need a way to identify the same logical turn across regenerated responses.

The combination of:

```text
external_turn_id
turn_version
status
snapshot
```

provides the necessary information to distinguish:

* new turns;
* repeated requests;
* regenerated responses;
* stale versions;
* conflicting payloads.

---

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
│   ├── Campaign services
│   ├── Context and memory services
│   ├── LLM services
│   ├── Turn resolution
│   ├── SillyTavern integration
│   └── World management
├── integrations/
│   └── External integration code
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
* LLM-based extraction;
* context and memory retrieval;
* SQLite persistence;
* REST API;
* SillyTavern integration;
* turn versioning;
* idempotency and conflict detection;
* snapshot-based regeneration reconciliation;
* rollback after failed regeneration;
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
