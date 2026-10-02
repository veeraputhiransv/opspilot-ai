# OpsPilot AI — HTTP API

Base path: `/api/v1`. OpenAPI at `/docs`. Errors:

```json
{ "error": { "code": "not_found", "message": "Incident not found" } }
```

422 validation, 401 unauthenticated, 403 forbidden (including policy), 409 approval conflict, 429 rate limit.

Times are ISO-8601 with timezone. Field names are snake_case.

See [AUTH.md](AUTH.md) for tokens and RBAC.

## Auth

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/auth/register` | User + org + default workspace |
| POST | `/auth/login` | Access + refresh |
| POST | `/auth/refresh` | Rotate refresh |
| POST | `/auth/logout` | Revoke refresh |
| GET | `/auth/me` | Current user, orgs, workspaces |
| POST | `/auth/workspace` | Mint access token for a workspace the user belongs to |

## Ingest

`POST /events` → `202` (or `200` if replayed) with a workspace API key or an operator JWT.

Body: `service`, `environment`, `event_type`, `error_rate`, `message`, `timestamp`. `extra=forbid`. Response: incident id and number.

### Idempotency

1. If the client sends `idempotency_key` (1–128 characters), that value is used as-is for the workspace.
2. Otherwise OpsPilot hashes:

`workspace_id | service | environment | event_type | error_rate | message | timestamp`

The pair `(workspace_id, idempotency_key)` is unique on `incident_events`.

A second request with the same key returns the original incident (`replayed: true`) and **does not** start another graph run. A different key always creates a new incident.

This is ingest-level idempotency, not alert-correlation across distinct outages.

## Demo scenarios (opt-in)

Available only when `OPSPILOT_DEMO_SEED_ENABLED=true` and the token is the AcmeFlow demo workspace.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/demo/scenarios` | Catalog of fictional scenarios |
| POST | `/demo/scenarios/{key}/trigger` | Ingest that scenario as a real incident |

See [DEMO.md](DEMO.md).

## Incidents

All list/get queries are workspace-scoped from the token.

| Method | Path | Roles |
| --- | --- | --- |
| GET | `/incidents` | viewer+ |
| GET | `/incidents/{id}` | viewer+ |
| GET | `/incidents/{id}/timeline` | viewer+ |
| GET | `/incidents/{id}/agent-runs` | viewer+ |
| POST | `/incidents/{id}/resolve` | operator+ |
| GET | `/incidents/{id}/rca` | viewer+ |
| GET | `/incidents/{id}/rca/export` | viewer+ |

No generic tool-execute endpoint.

## Approvals

| Method | Path | Roles |
| --- | --- | --- |
| GET | `/approvals` | viewer+ |
| POST | `/approvals/{id}/approve` | operator+ |
| POST | `/approvals/{id}/reject` | operator+ |
| POST | `/approvals/{id}/modify` | operator+ |

## Knowledge, dashboard, settings, stream

Existing read routes remain, workspace-scoped. Settings writes are admin+. SSE uses a short-lived stream ticket (`POST /realtime/tickets`, then `GET /events/stream?ticket=...`). Access JWTs are not accepted in the query string.

## Health

`GET /health` liveness. `GET /health/ready` checks Postgres (and Redis if required).
