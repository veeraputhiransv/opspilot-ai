# OpsPilot AI — Database Design

PostgreSQL 16 with `vector`. Primary keys are UUIDs. Timestamps are `timestamptz` written in UTC.

JSONB is only for: raw ingest payloads, tool argument/result snapshots, evidence lists, audit detail, workflow cursor. Status, severity, risk, email, and roles are columns.

Incident, knowledge, and audit tables are workspace-scoped (`organization_id` + `workspace_id`). Incident numbers are unique per workspace.

---

## Identity

### organizations

| Column | Notes |
| --- | --- |
| id | UUID PK |
| name | Display |
| slug | Unique, URL-safe |
| status | `active`, `suspended` |
| created_at, updated_at | |

### workspaces

| Column | Notes |
| --- | --- |
| id | UUID PK |
| organization_id | FK, cascade restrict |
| name | Display |
| slug | Unique per organization |
| status | `active`, `archived` |
| created_at, updated_at | |

Unique `(organization_id, slug)`. Index `organization_id`.

### users

| Column | Notes |
| --- | --- |
| id | UUID PK |
| email | Unique, stored lowercased |
| password_hash | Nullable so a future SSO-only user can exist; email/password users always have a hash |
| full_name | |
| status | `active`, `disabled` |
| email_verified_at | Nullable |
| created_at, updated_at | |

### organization_members

| Column | Notes |
| --- | --- |
| id | UUID PK |
| organization_id | FK |
| user_id | FK |
| role | `owner`, `admin`, `member` |
| created_at, updated_at | |

Unique `(organization_id, user_id)`.

### workspace_members

| Column | Notes |
| --- | --- |
| id | UUID PK |
| workspace_id | FK |
| user_id | FK |
| role | `admin`, `operator`, `viewer`, `auditor` |
| created_at, updated_at | |

Unique `(workspace_id, user_id)`. A workspace admin must also be an organization member.

### refresh_tokens

| Column | Notes |
| --- | --- |
| id | UUID PK |
| user_id | FK |
| token_hash | SHA-256 of the opaque token |
| expires_at | |
| revoked_at | Nullable |
| created_at | |
| user_agent | Optional, truncated |

Index `(user_id, expires_at)`.

### identity_providers

SSO-ready. Unused until OAuth is implemented. No fake login.

| Column | Notes |
| --- | --- |
| id | UUID PK |
| organization_id | FK |
| type | `oidc`, `github`, `google` |
| issuer | Nullable until configured |
| client_id | |
| client_secret_encrypted | Nullable; never returned by API |
| enabled | Boolean default false |
| created_at, updated_at | |

Unique `(organization_id, type)`.

### user_identities

| Column | Notes |
| --- | --- |
| id | UUID PK |
| user_id | FK |
| provider | String matching identity_providers.type or `password` |
| subject | IdP subject |
| email | Snapshot |
| created_at | |

Unique `(provider, subject)`.

### workspace_api_keys

Ingest credentials. The raw secret is shown once at creation.

| Column | Notes |
| --- | --- |
| id | UUID PK |
| workspace_id | FK |
| name | |
| key_prefix | First 8 chars for identification |
| key_hash | |
| scopes | JSON list, default `["events:write"]` |
| last_used_at | |
| revoked_at | |
| created_by_user_id | FK nullable |
| created_at | |

---

## Operations (existing tables, tenant columns added)

### incident_counters

One row per workspace (`workspace_id` PK/FK) holding `next_number`. Allocation is `UPDATE … RETURNING`.

### incidents

Add `organization_id`, `workspace_id` (indexed, required). Keep current columns: incident_number unique **per workspace** (`UNIQUE (workspace_id, incident_number)`), service, environment, event_type, scenario_key (optional label for adapters; not a security control), severity, status, title, summary, message, error_rate, current_activity, model_used, token rollups, last_error, started_at, resolved_at, timestamps.

Indexes: `(workspace_id, status)`, `(workspace_id, created_at DESC)`, `(workspace_id, service)`.

### incident_events, incident_timeline, agent_runs, agent_steps, tool_calls, incident_hypotheses, incident_actions, approval_requests, approval_decisions, workflow_checkpoints, rca_reports

Unchanged purpose. They hang off `incidents` and inherit tenancy through that FK. `approval_decisions.actor` becomes `actor_user_id` (UUID, nullable for system) plus `actor_label` for display.

### customer_reports

Add `workspace_id`. Support signals are source data, not a blob on the incident.

### knowledge_documents

Add `workspace_id`, `source_type` (`prior_incident`, `runbook`, `markdown`, `pdf`), `external_id` unique per workspace.

### incident_embeddings

Unchanged: one `vector(384)` per document, model name stored, HNSW cosine. Dimension change requires a migration.

### audit_logs

Add `organization_id`, `workspace_id` (nullable for org-level events), `actor_user_id`, `actor_api_key_id`, `actor_type` (`user`, `api_key`, `system`). Keep action, resource_type, resource_id, incident_id, detail JSONB, created_at. Index `(workspace_id, created_at)`, `(actor_user_id, created_at)`.

---

## What is not a table

Live application logs and Git history remain external. Adapters return snapshots stored on `tool_calls`. The agent only reasons over what was persisted.

---

## Migrations

Applied via `alembic upgrade head` from `backend/alembic/versions/`:

- `001_initial` — incident, evidence, and workflow tables
- `002_identity_and_tenancy` — organizations, workspaces, users, RBAC, per-workspace incident numbers
- `003_vertical_slice` — ingest idempotency, evidence snapshots, RCA versions, execution guards
- `004_hardening` — vault tables, execution reliability, stream-ticket storage

Demo and development users are created by application seeders (`scripts/seed_demo.py`) or `POST /auth/register`. Optional bootstrap credentials apply only when `OPSPILOT_BOOTSTRAP_ENABLED=true`.
