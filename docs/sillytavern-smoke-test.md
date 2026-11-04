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

5. **Chat change / reset**
   - Switch to a different SillyTavern chat.
   - Generate a response in the new chat.
   - Confirm the new chat starts with its own turn identity and that no local processing/failure marker from the previous chat blocks it.
   - Return to the original chat and verify that persisted backend state is reloaded rather than inferred from stale local cache.

## Acceptance criteria

- Each distinct regeneration is processed at most once.
- A duplicate delivery does not reapply consequences.
- A failed, uncommitted version can be retried.
- Switching chats clears local turn-version, narrative, processing, and failure state.
- The backend remains authoritative when local state is reset.

## Recording the result

Record the date, backend revision, extension revision, and outcome for each checklist item when performing the manual test. Do not mark this checklist as passed based solely on unit or CI tests.
