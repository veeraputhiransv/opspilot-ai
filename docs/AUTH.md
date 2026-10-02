# OpsPilot AI — Authentication and Authorization

## Goals

- Email/password is the primary path for humans.
- Architecture is ready for OAuth/SSO without rewriting incidents.
- Demo workspace is not a substitute for auth.
- Browser never receives integration or LLM secrets.

## Tokens

Access token: JWT, HS256 in v1 (secret from env). Claims:

```json
{
  "sub": "<user uuid>",
  "org": "<organization uuid>",
  "ws": "<workspace uuid>",
  "roles": ["operator"],
  "typ": "access",
  "exp": 0
}
```

Lifetime: 15 minutes. The console sends `Authorization: Bearer`. Query-string access tokens are not accepted.

## Realtime stream tickets

`EventSource` cannot set Authorization headers. The console mints a short-lived ticket:

1. `POST /api/v1/realtime/tickets` with a Bearer access token (workspace, and optional incident, already authorized)
2. `GET /api/v1/events/stream?ticket=...`

The ticket is a random secret stored hashed, TTL ~90 seconds, capped reuse for reconnects. It is not a JWT and cannot call REST APIs.

Refresh token: opaque, stored hashed in `refresh_tokens`, rotating on use, HTTP-only cookie on the API host or returned to the Next.js BFF. Revoke on logout.

Workspace selection: after login the user picks a workspace they belong to (or uses the last workspace). Subsequent access tokens are minted for that `(org, workspace)`. Switching workspace issues a new access token.

## Password

Argon2id (or bcrypt if Argon2 is unavailable in the image). Minimum length 12. Timing-safe compare. No password in logs or audit detail.

## Registration and login

`POST /api/v1/auth/register` creates a user, an organization they own, a default workspace, org owner membership, and workspace admin membership.

`POST /api/v1/auth/login` verifies email/password and issues tokens.

`POST /api/v1/auth/refresh` and `POST /api/v1/auth/logout` rotate or revoke refresh tokens.

Email verification can ship as a later hardening step; the column exists from day one.

## Ingest authentication

`POST /api/v1/events` requires `Authorization: Bearer ops_live_...` matching a non-revoked workspace API key with `events:write`. The incident is created in that key’s workspace. User JWTs may also ingest if the user is `operator` or above (console “report event”). Unauthenticated ingest is not allowed in production configuration.

Local development: `OPSPILOT_AUTH_DISABLED=true` is forbidden in `mode=real`. For tests, fixtures mint a user and key.

## RBAC enforcement

FastAPI dependencies: `get_current_user`, `require_workspace`, `require_roles(*roles)`. Services receive `AuthContext(user_id, organization_id, workspace_id, roles)` and must filter every query by workspace_id. Missing workspace filter is a defect, not a feature.

## SSO later

`identity_providers` and `user_identities` are created in the identity migration. OIDC callback routes are added when SSO is implemented. Until then, `enabled=false` and no login buttons that pretend SSO works.

## Operator attribution

Approval and audit use `actor_user_id` from the JWT. Operator identity is never taken from a free-text request header.
