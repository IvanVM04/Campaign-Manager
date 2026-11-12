# SillyTavern adapter boundary — 2026-11-12

## Purpose

Move external-platform translation out of the capability-service tree and separate active read behavior from the deprecated narrative-first mutation workflow. This is an ownership and dependency change only; it does not retire the compatibility endpoint.

## Resulting structure

- integrations/adapters/silly_tavern/context_adapter.py — read-only campaign context/history and external transcript-state translation.
- integrations/adapters/silly_tavern/service.py — thin runtime-facing façade. It delegates reads to the context adapter and delegates deprecated turn processing through a small processor protocol.
- integrations/adapters/silly_tavern/errors.py — stable integration error types translated by the HTTP router.
- services/turns/legacy_silly_tavern_turn_service.py — unchanged legacy narrative-first turn processing, idempotency, snapshot reconciliation and transaction behavior.
- bootstrap/campaign_runtime.py — composition root. It builds the context adapter and legacy turn service separately, injects their dependencies and assembles the façade.

## Dependency direction

1. HTTP routers use request-scoped runtime services and map integration errors to HTTP responses.
2. The integration adapter translates external contracts and delegates to application services/use cases.
3. Capability packages do not import the integration adapter.
4. The integration adapter does not import API routers or bootstrap.
5. Bootstrap owns cross-package composition, including CampaignStateVersionRepository and WorldSnapshotRepository construction for the deprecated route.

The active context adapter no longer imports or constructs an LLM extractor, world mutation service, snapshot repository, campaign-state version repository, legacy turn service or transaction helper. The façade does not own those dependencies.

## Compatibility preserved

- POST /integration/turn remains deprecated but operational.
- Resolve/complete, context, external transcript-state, clarification and manual-roll routes retain their existing paths and response shapes.
- SillyTavernIntegrationService remains the runtime-facing property name.
- Legacy idempotency, revision checks, rollback and snapshot regeneration remain owned by LegacySillyTavernTurnService.
- No historical snapshot JSON or turns.snapshot schema is changed.
- The manual SillyTavern smoke test and live Ollama probes remain separate from deterministic CI.

## Regression coverage

- Existing SillyTavern HTTP, context, transcript-state, idempotency, regeneration and rollback tests are migrated to the canonical integration package.
- Test fixtures compose the same adapters explicitly.
- Architecture tests prevent capability services from importing external integration adapters and prevent the adapter package from importing transport/composition layers.
- The old root module under services/ is asserted absent.

## Deferred work

- Do not remove the deprecated mutation route until production logs show zero usage for an agreed observation window and supported client versions have signed off.
- Do not remove snapshot compatibility or the nullable turns.snapshot column until a separate retention/migration decision is approved.
- Do not add new gameplay behavior to the legacy service.
