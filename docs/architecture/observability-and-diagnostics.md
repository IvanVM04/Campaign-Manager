# Observability and diagnostics

**Scope:** local, single-player, single-process runtime.  
**Introduced:** PR #208.  
**Purpose:** make failures and slow operations diagnosable without changing
business behavior, exposing internals to the player or requiring a live
debugging session.

## Two distinct information channels

### Technical logs

Technical logs are intended for local troubleshooting and developer support.
They are emitted to console and, by default, a rotating JSON-lines file at
`logs/campaign-manager.jsonl`. The `/logs/` path is ignored by Git.

The `observability` package owns:

- `LoggingSettings` and `configure_logging()`: one validated configuration
  for root logging, console format and a rotating local file handler.
- `JsonLineFormatter`: timestamped structured records with a field allowlist.
- `log_context`: request/campaign/resolution IDs propagated with ContextVars.
- `RequestObservabilityMiddleware`: accepts a safe `X-Request-ID` or creates
  one, binds request/campaign correlation, records request duration/status and
  returns the ID in the `X-Request-ID` response header.

The model-facing intent, mechanics and extraction roles emit provider
success/failure events with role, configured/response model, UTF-8 prompt byte
count, response character count, stable error type and request duration. When
Ollama returns them, the adapter also records prompt/evaluation token counts,
raw server durations and derived millisecond timings, completion status and
done reason. The optional live-evaluation callback receives the same
content-free metadata in memory. Optional Ollama version and model-digest
lookups identify the local runtime without logging its prompts or outputs.

The structured proposal path separately records prompt/context sizes, budget
utilization, selected/excluded record counts, validated operation family/count
and repair outcome. The JSON-lines formatter has an explicit allowlist for
these bounded diagnostic fields. It does not store prompts, raw completions,
player input or campaign prose.

## Configuration

| Environment variable | Default | Meaning |
|---|---|---|
| `CAMPAIGN_MANAGER_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` |
| `CAMPAIGN_MANAGER_LOG_CONSOLE_FORMAT` | `text` | `text` or `json` console output |
| `CAMPAIGN_MANAGER_LOG_FILE` | `logs/campaign-manager.jsonl` | Local rotating JSONL file; set `off` to disable |
| `CAMPAIGN_MANAGER_LOG_MAX_BYTES` | `10485760` | Maximum size of each log file before rotation |
| `CAMPAIGN_MANAGER_LOG_BACKUP_COUNT` | `5` | Rotated file count retained (0–100) |

Each JSON line has timestamp, severity, logger name and safe message plus
approved correlation and diagnostic fields. File rotation bounds disk use.
The configuration replaces only handlers created by this package; it does
not delete arbitrary application or third-party handlers.

## Correlation contract

- Clients may send `X-Request-ID` using 1–64 ASCII characters from letters,
  digits, dot, underscore and hyphen. Invalid values are replaced with a
  generated UUID hex value.
- Every HTTP response includes `X-Request-ID`; CORS exposes that header to
  the local browser UI.
- The same ID is attached to log records for the request. The campaign ID is
  attached when a valid positive `X-Campaign-Id` is present.
- Once a durable resolution record exists, its ID is bound while mechanics,
  proposal and narration provider calls execute, so model diagnostics can be
  joined to the HTTP request and durable turn.
- Request IDs are diagnostic correlation only. They are not authentication,
  authorization, idempotency keys or proof that a request is trusted.

## Safe diagnostics and redaction

Structured output uses an explicit allowlist. It intentionally excludes
arbitrary `extra` fields, prompt text, raw model responses, user input,
campaign narrative, entity notes and secret world records. Common credential
patterns and bearer tokens in log messages/exception traces are redacted.
Callers should log stable error types/codes and counts instead of sensitive
payloads.

Do not add:
- full prompts, completions or clarification text;
- passwords, API keys, authorization headers or provider credentials;
- secret events, GM-only notes or unrestricted serialized world state;
- raw request bodies or unrestricted exception details in API responses.

HTTP errors retain the stable `code` / `detail` envelope and now echo
`X-Request-ID`. Unexpected exceptions keep their stack trace server-side,
with a generic client-safe 500 response.

## Technical logs are not the activity timeline

Do not make the future player interface read a log file or parse log messages.
PR #209 is planned as a separate typed, campaign-scoped activity history for
important player-visible transitions, with explicit safe read models and
pagination. Technical logs remain diagnostic, rotatable and potentially
verbose; activity history is durable product data with a different visibility
and retention contract.

## Validation

PR #208 tests cover settings validation, JSON field allowlisting, secret
redaction, nested ContextVar restoration, accepted/generated request IDs,
response-header propagation, validation errors and unexpected error
sanitization. CI validates the deterministic implementation. Real Ollama and
SillyTavern acceptance remains a later local-environment gate.
