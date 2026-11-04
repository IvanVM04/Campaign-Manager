# SillyTavern integration smoke test

This checklist validates the SillyTavern integration against a running Campaign Manager backend.
It is a manual integration check and is not replaced by the automated JavaScript test suite.

## Preconditions

- Campaign Manager backend is running and reachable from the SillyTavern extension.
- The extension is installed and configured with a valid campaign.
- A test chat is available; use a disposable campaign or a state that can safely be changed.

## Checklist

1. **Initial generation (V1)**
   - Send a player message that causes the DM to generate a response.
   - Confirm the response is processed and the corresponding turn is persisted as version 1.

2. **Duplicate delivery**
   - Trigger or reproduce delivery of the same generated turn again without changing its narrative.
   - Confirm the turn is not applied twice and no duplicate consequences are persisted.

3. **Regeneration (V2 and V3)**
   - Regenerate the assistant response with a different narrative.
   - Confirm the new response is processed as the next version.
   - Regenerate once more with another narrative and confirm the version advances again.

4. **Failure and retry**
   - In a disposable test, make the backend unavailable during turn processing, then restore it.
   - Retry the same generated turn.
   - Confirm the failed attempt did not consume an active version and the retry can be processed.

5. **Single clarification**
   - Trigger an ambiguous action that makes Campaign Manager ask a clarification question.
   - Reply with the missing detail.
   - Confirm the reply continues the original action, the world consequences are committed once, and the generated narrative is stored under the original external turn ID.

6. **Multiple clarification rounds**
   - Use an action that requires two clarification questions.
   - Answer both questions.
   - Confirm the second answer continues the same durable resolution and neither answer is recorded as a separate player action.

7. **Restart recovery**
   - Stop/reload the browser or extension while a clarification is pending.
   - Reopen the same chat and answer the pending question.
   - Repeat after submitting an answer but before narration is generated.
   - Confirm the extension recovers the active/last challenge from the backend and retries without duplicate consequences.

8. **Normal action after clarification**
   - Complete a clarified action, then send a new ordinary player action.
   - Confirm the new action receives its own external turn ID and is not mistaken for a repeated clarification answer.

9. **Chat change / reset**
   - Switch to a different SillyTavern chat.
   - Generate a response in the new chat.
   - Confirm the new chat starts with its own turn identity and that no local processing/failure marker from the previous chat blocks it.
   - Return to the original chat and verify that persisted backend state is reloaded rather than inferred from stale local cache.


10. **Manual dice — normal roll**
    - Set Dice mode to Manual rolls in the Campaign Manager extension settings.
    - Trigger an ability check, skill check or saving throw.
    - Confirm the DM asks for one d20 result and shows the server-computed modifier and DC.
    - Reply with a single integer from 1 to 20.
    - Confirm the backend resolves the check and the narrative is stored against the original action, not the numeric reply.

11. **Manual dice — advantage/disadvantage**
    - Trigger a check with advantage, then enter two comma-separated d20 results.
    - Repeat with disadvantage.
    - Confirm the backend selects the correct die, applies the modifier once and computes success/failure.
    - Confirm one result is rejected when two are required, and values outside 1–20 are rejected.

12. **Manual dice — restart and idempotency**
    - Reload the extension while a manual roll is pending.
    - Reply with the required result(s) and confirm the challenge is recovered from the backend.
    - Retry the exact same result submission and confirm no consequences are applied twice.
    - Submit different results for an already accepted challenge and confirm the backend rejects them.
    - Switch back to Automatic rolls and confirm the default automatic flow works again.

## Acceptance criteria

- Each distinct regeneration is processed at most once.
- A duplicate delivery does not reapply consequences.
- A failed, uncommitted version can be retried.
- Clarification answers resume the original action, including across reloads and multiple clarification rounds.
- Manual dice challenges recover across reloads, accept only the required number of valid d20 results, and commit the original turn at most once.
- A subsequent ordinary action receives a new external turn identity.
- Switching chats clears local turn-version, narrative, processing, failure, and clarification-link state.
- The backend remains authoritative when local state is reset.

## Recording the result

Record the date, backend revision, extension revision, and outcome for each checklist item when performing the manual test. Do not mark this checklist as passed based solely on unit or CI tests.
