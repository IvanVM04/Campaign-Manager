# Phase 0 — architecture closeout and hand-off

**Scope:** local, single-player, single-process modular monolith.

## Decision
The architecture is sufficiently modular for the current product scope.
Do not start another broad decomposition, microservices, distributed
infrastructure, multi-user authorization or standalone UI before gameplay
demonstrates a concrete need. PRs #198–#202 retired the parallel turn path,
centralized visibility, extracted durable execution, hardened combat writes,
coordinated world operations, split request schemas and indexed migrations.

## Preserved compatibility/history
Do not delete `turn_snapshot_archive`, `models.schemas`, the legacy
`npc_melee_attack` read fallback or historical migrations merely as cleanup.
They preserve data/import compatibility/history and are not active parallel
runtime paths.

## Remaining P1 gate
- Run the local Ollama + SillyTavern acceptance flow: campaign setup,
  exploration, checks, clarification, manual/automatic dice, combat where
  applicable, persistence, restart/recovery and provider outage. Record model
  and settings; deterministic CI cannot prove model quality.

The cross-workflow state audit for mechanics currently implemented in the
repository is documented in
[the combat/character-state audit](combat-character-state-audit-2026-11-12.md)
and addressed in the character-rest/combat-consistency PR. That work does not
claim that future class resources, spell slots or rest interruptions exist;
those require their own typed rules and persistence contracts.

## Remaining P2
- Split the largest turn/context test modules by observable contract, preserving assertions.
- Target critical branches: rollback, provider errors, stale state, lease fencing,
  restart recovery, resource handling and effect expiry. Treat 73.2% branch
  coverage as diagnostic, not a global gate.
- Run representative large-campaign context/proposal probes with Ollama opt-in.

## Deferred by product scope
No multiplayer, accounts, remote exposure, multiple workers, distributed locks,
automatic LRU/TTL cache eviction without measured need, standalone UI or full
D&D 5e implementation. Implement rules in deterministic tested slices.

## Development hand-off
After the P1 combat audit and live acceptance, focus on gameplay: persisted
character creation, equipment/resources, core combat/rest loop and one complete
first adventure. Refactor further only when a real ownership/testability issue
appears.
