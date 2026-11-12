# Package dependency matrix

This document records allowed dependency direction for the modular monolith.
It complements the [architecture map](architecture-map-2026-11-12.md) and
is enforced by the architecture-boundary tests.

## Dependency direction

- API routers depend on transport schemas, runtime context and application
  services; application logic does not import routers.
- Bootstrap is the composition root. Capability packages do not import
  bootstrap or construct their own process-wide runtime.
- Capability application services may depend on shared models, repositories,
  operations, rules-engine contracts and explicitly injected collaborators.
- The rules engine remains pure: it does not import services, repositories,
  database code, FastAPI or provider clients.
- `services/turns` may orchestrate `services/context` and
  `services/llm_world`; `services/llm_world` must not import
  `services/context`.
- `integrations/adapters/silly_tavern` may depend on public application
  contracts and read-oriented context adapters. Capability services must not
  import external integration adapters.

## SillyTavern composition

- `SillyTavernContextAdapter` owns active context/history and external
  transcript-state read translation.
- `SillyTavernIntegrationService` is a thin read-oriented façade.
- `bootstrap/campaign_runtime.py` builds the context adapter and wires it
  into the facade.
- Turn mutation remains owned by `DurableNativeTurnService` and its
  collaborators, not by the integration adapter.

## Retired dependency paths

Do not recreate the narrative-first `POST /integration/turn`,
`LegacySillyTavernTurnService`, `WorldSnapshotRepository`, or a
compatibility `process_turn()` delegate. The active external client uses the
durable resolve/complete lifecycle.

## Rules for adding dependencies

1. Prefer an existing owning package or a narrow injected protocol.
2. Add the import edge to this matrix and an architecture test in the same PR.
3. Avoid circular imports and package-level reexports that recreate old flat
   module paths.
4. Do not make domain/rules packages aware of HTTP, integrations, or provider
   implementations.
