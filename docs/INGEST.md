# Event ingest idempotency

`POST /api/v1/events` is authenticated with a workspace ingest API key or an operator JWT. The request is validated (`extra=forbid`) and then stored.

## Correlation key

1. If the client sends `idempotency_key` (1–128 characters), that value is used as-is for the workspace.
2. Otherwise OpsPilot hashes:

`workspace_id | service | environment | event_type | error_rate | message | timestamp`

The pair `(workspace_id, idempotency_key)` is unique on `incident_events`.

## Retry behavior

A second request with the same key returns the original incident (`replayed: true`) and **does not** start another graph run. A different key always creates a new incident.

This is ingest-level idempotency, not alert-correlation across distinct outages. Distinct messages or timestamps without a shared client key create distinct incidents.
