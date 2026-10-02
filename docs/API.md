# OpsPilot AI — HTTP API

Base path: `/api/v1`. OpenAPI at `/docs`. Errors:

```json
{ "error": { "code": "not_found", "message": "Incident not found" } }
```

422 validation, 401 unauthenticated, 403 forbidden (including policy), 409 approval conflict, 429 rate limit.

Times are ISO-8601 with timezone. Field names are snake_case.

This document replaces the open-demo auth described in the old API sketch. See [AUTH.md](AUTH.md).

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

`POST /events` → `202` with workspace API key or operator JWT.

Body unchanged: `service`, `environment`, `event_type`, `error_rate`, `message`, `timestamp`. `extra=forbid`. Response: incident id and number.

`GET /demo/scenarios` is **removed until phase 23**. Development uses eval fixtures in pytest, not a public scenario endpoint that implies the product is a scripted demo.

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

Existing read routes remain, workspace-scoped. Settings writes are admin+. SSE uses the access token (`Authorization` or `access_token` query for EventSource).

## Health

`GET /health` liveness. `GET /health/ready` checks Postgres (and Redis if required).
