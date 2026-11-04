# API error response contract

**Status:** Introduced in PR #21  
**Scope:** HTTP transport responses only

## Response shape

Error responses use a stable top-level `code` while retaining the existing `detail` field:

```json
{
  "detail": "The supplied version is stale.",
  "code": "conflict"
}
```

The `detail` value remains a string for existing HTTP exceptions and may be a structured list for request validation errors. Clients should branch on `code`, not parse human-readable detail text.

## Standard codes

| HTTP status | Code | Meaning |
| --- | --- | --- |
| 400 | `bad_request` | Request cannot be processed as supplied |
| 401 | `unauthorized` | Authentication is required |
| 403 | `forbidden` | Operation is not permitted |
| 404 | `not_found` | Resource does not exist in the requested scope |
| 405 | `method_not_allowed` | HTTP method is unsupported |
| 409 | `conflict` | Current state conflicts with the requested operation |
| 422 | `validation_error` | Request shape or field validation failed |
| 429 | `rate_limited` | Request rate limit was exceeded |
| 503 | `service_unavailable` | A required dependency is unavailable |
| 500 | `internal_error` | Unexpected server-side failure |

Application-specific errors may use a more precise stable code through `APIError`, while retaining an appropriate HTTP status.

## Compatibility and security

- Existing HTTP status codes are preserved by the global HTTP exception handler.
- The `detail` field is retained for existing clients.
- FastAPI validation errors expose location, message and validation type, but omit submitted input values and internal context.
- Unexpected exceptions are logged server-side and return a generic `500 internal_error` response.
- Internal exception messages and stack traces must not be returned to clients.
- The campaign runtime middleware uses the same response envelope as route-level errors.
- Successful response payloads are unchanged.

## Migration guidance for clients

Use `code` for programmatic handling. Treat `detail` as display/debug context, not a stable identifier. Validation `detail` is a list of field errors; other details are generally strings.

## Deliberate non-goals

This contract does not yet replace every service exception with a domain-specific application exception. Existing route mappings remain in place to avoid an unsafe, repository-wide semantic change. Subsequent work can progressively replace generic `HTTPException` construction with typed `APIError` instances and test each mapping independently.
