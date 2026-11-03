# Campaign clock

Each campaign has an authoritative fictional-time clock, measured as elapsed minutes from the campaign's starting point. It is deliberately independent of server wall-clock time and does not assume a particular fantasy calendar, date, or timezone.

## API

All campaign-scoped endpoints require the existing `X-Campaign-Id` header.

- `GET /campaign/clock` returns the current elapsed minutes and clock version. Existing campaigns are initialized at minute zero by migration 019; the service also safely initializes a missing clock row.
- `POST /campaign/clock/advance` advances fictional time. The request supplies a positive `minutes` value and `expected_elapsed_minutes` from the last read. A stale expected value returns HTTP 409 rather than overwriting a concurrent advance.

The maximum single advance is 525,600 minutes (one fictional year of 365 days). Multiple advances can be made for longer jumps.

## Boundaries

Advancing the clock and expiring due campaign-time effects happen in the same SQLite transaction. If expiration fails, the clock advance rolls back as well. Expired effects retain their history and are returned with status `expired` when `include_removed=true` is requested on the entity-effects endpoint. The clock does not advance combat rounds/turns or infer elapsed time from server timestamps.