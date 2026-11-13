# SillyTavern durable turn adapter

**Status:** active, implemented through the durable native turn application
service. The former narrative-first compatibility route has been removed.

## Request sequence

1. The generation interceptor identifies the latest user message, reads the
   current SillyTavern chat ID and derives the stable external turn ID from
   chat identity and message index. Every context/resolve/continuation request
   also carries the required `conversation_id`.
2. Before SillyTavern generates prose, it calls
   `POST /integration/turn/resolve`, including the configured `dice_mode`
   (`automatic` by default, or `manual`).
3. The backend uses `DurableNativeTurnService` with adapter namespace
   `sillytavern`. The external turn ID is the durable idempotency key.
4. The coordinator plans structured consequences from player intent, validates
   them, and commits them with the resolution record and resulting campaign
   revision in one transaction.
5. The endpoint returns the current campaign context and committed resolution
   evidence. The extension injects both into SillyTavern's generation prompt.
   If manual mode requires a roll, the response contains a pending challenge;
   the extension requests the result and does not complete a transcript yet.
6. After generation, the extension calls
   `POST /integration/turn/complete`. This stores the external narrative and
   completes the transcript projection; it does not apply domain operations.
7. If generation or completion fails after commit, the next generation reuses
   the same resolution. It does not replan or reapply consequences.

## Regeneration and swipes

A stable external turn ID represents the player message, not an individual
assistant swipe. The first completed narrative is version 1. A different swipe
creates the next transcript version and supersedes the prior narrative record.
All versions reference the same committed domain outcome. No snapshot restore,
reroll or consequence replay occurs during a swipe.

Exact retries of a narrative version return the existing transcript. Reusing a
version with different narrative content, submitting an older version or
skipping a version is rejected.

## Historical transcript compatibility

- `GET /integration/turn/{external_turn_id}` continues to expose the active
  transcript version for read/cache recovery.
- `POST /integration/turn` has been removed and returns 404.
- A historical transcript without a corresponding durable resolution remains
  historical read data only. It cannot be used to create a new narrative
  version or mutate the campaign. A new player action must use a new external
  turn ID and the durable `resolve -> complete` lifecycle.
- Completion requires the same stable external turn ID used for resolution.

## Durable clarification continuation

1. If `POST /integration/turn/resolve` returns
   `lifecycle_state=awaiting_input`, it also returns a
   `pending_clarification_id`. The extension asks the player the clarification
   question; no transcript is completed yet.
2. When the player replies, the extension searches recent chat history for the
   original action and checks durable clarification state through
   `GET /integration/turn/{external_turn_id}/clarification`.
3. It submits the answer to `POST /integration/turn/clarification`, using the
   original challenge ID and current `conversation_id`. The backend verifies
   the challenge belongs to that chat before resuming the resolution and
   returns another clarification or committed resolution evidence.
4. Once the resolution is committed, SillyTavern generates the narrative. The
   extension completes the transcript using the original external turn ID and
   original player input, not the clarification answer as a new action.
5. The clarification-state endpoint exposes the active challenge and last
   accepted challenge/answer. This lets the extension retry safely after a
   browser refresh without storing challenge tokens as local source of truth.

The extension searches a bounded recent history (24 messages) when
reconstructing the original action. The backend remains authoritative; if it
cannot verify clarification state, generation is aborted rather than treating
an unverified answer as a new action.

## Durable manual dice continuation

1. The extension sends `dice_mode=manual` when selected in extension settings.
   Automatic remains the default.
2. When mechanics require a d20, the backend stores the challenge, dice count,
   ability/skill, DC, modifier, advantage/disadvantage and context revision in
   the existing `turn_resolutions` record with
   `lifecycle_state=awaiting_input`. The extension receives only an opaque
   challenge identifier.
3. The extension requests exactly one result for a normal roll, or two
   comma/semicolon-separated results for advantage/disadvantage. Values must
   be integers from 1 to 20.
4. It submits results to `POST /integration/turn/roll` using the durable
   challenge ID. The backend validates count and values, computes mechanics,
   commits consequences and returns committed resolution evidence.
5. The roll reply is linked to the original external turn ID. It is not a new
   action or separate transcript. Generated narration is completed against
   the original action.
6. `GET /integration/turn/{external_turn_id}/manual-roll` reconstructs a
   pending challenge after browser/extension restart. Re-submitting accepted
   results is idempotent; different results for an accepted challenge are
   rejected.

The manual-roll API is adapter-scoped to `sillytavern`. Challenge metadata
omits internal adjudication decisions and challenge-token details beyond the
opaque submission ID.

## Deliberate limitations

- Manual dice cover the currently supported d20 ability checks, skill checks
  and saving throws. Other dice expressions require explicit engine support.
- There is no background recovery worker. Recovery is request-driven through
  durable challenge and turn identities.
- A generation failure after consequence commit leaves the resolution in
  `narration_pending`; retrying the same external action safely resumes
  narration without applying consequences again.


## Conversation isolation

The API requires and propagates the stable `conversation_id` for context retrieval, turn resolution, clarification and manual-roll submissions. Migration 034 stores it on transcript turns and durable resolutions; recent history is filtered by campaign, session and chat. Clarification/manual-roll continuations reject a challenge submitted from another chat. Legacy rows remain nullable and are never assigned a guessed chat identity. The extension must fail closed when it cannot supply the current chat ID.
