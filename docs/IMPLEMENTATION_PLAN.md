# OpsPilot AI — Implementation Plan

> **For agentic workers:** Implement phase by phase. Each phase must leave the repository runnable. Do not skip to the seeded LinkedIn workspace. Do not replace the investigation graph unless a phase explicitly requires it.

**Goal:** Evolve the existing OpsPilot modular monolith from a demo-open incident engine into a production SaaS control plane with identity, RBAC, real workflows, and a late demo seed.

**Architecture:** Approach B in [ARCHITECTURE.md](ARCHITECTURE.md) — one FastAPI app, Postgres system of record, Redis fan-out, LangGraph investigation, policy as code, integration and LLM protocols.

**Tech stack:** FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, PostgreSQL 16 + pgvector, Redis, Next.js, TypeScript, Tailwind, pytest.

## Global constraints

- Product identity is OpsPilot AI — Autonomous AI Incident Response & Operations Platform.
- Modular monolith only. No microservices.
- Email/password primary auth; SSO tables ready; demo workspace last.
- Do not fake backend behavior for the UI.
- External systems may use mock adapters; persist real tool_call rows.
- Deterministic reasoner remains the default for tests.
- User JWT is not the ingest story; workspace API keys ingest events.
- Never hardcode secrets.

---

## Mapping to the existing repo

Phases 6–17 of the product already have substantial implementations (ingest, SSE, graph, tools, RAG, approval, execution, RCA, inspector, eval). They were built **without tenancy**. Later phases **scope and harden** them rather than rewrite them.

| Phase | Name | Status entering this plan |
| --- | --- | --- |
| 1 | Architecture and domain | Documents in `docs/` |
| 2 | Database schema and migrations | `001_initial` plus `002_identity_and_tenancy` |
| 3–4 | Backend foundation + auth/RBAC | In progress in this repository: JWT, orgs, workspaces, ingest keys |
| 5 | Frontend shell and design system | Console exists; add login and workspace switch |
| 6 | Incident/event ingestion | Exists; bind to workspace keys |
| 7 | Real-time streaming | Exists; authorize SSE |
| 8 | Agent orchestration | Exists; pass workspace in context |
| 9 | Tool framework | Exists; keep typed registry |
| 10 | RAG / incident memory | Exists; filter by workspace |
| 11 | Human approval | Exists; require operator JWT |
| 12 | Action execution | Exists; fail closed in real mode |
| 13 | GitHub / comms / ops integrations | Mock + partial real clients; complete adapters |
| 14 | RCA | Exists |
| 15 | Agent observability | Exists |
| 16 | Audit logging | Rows exist; bind to user ids |
| 17 | Evaluation | Five scenarios exist; keep without live LLM |
| 18 | Settings and administration | Read-mostly; add members and keys |
| 19 | Security hardening | Headers, injection tests partial |
| 20 | Automated tests | Expand identity and tenancy tests |
| 21 | Docker/local deployment | Compose exists; auth env required |
| 22 | Production deployment notes | README later |
| 23 | Seed/demo workspace | Last data seed |
| 24 | Landing page | After product is real |
| 25 | LinkedIn scenario | After seed |

---

## Phase 1 — Architecture (done when these files exist)

- [x] `docs/ARCHITECTURE.md`
- [x] `docs/DOMAIN.md`
- [x] `docs/DATABASE.md`
- [x] `docs/AUTH.md`
- [x] `docs/AI_AGENT.md`
- [x] `docs/AGENT_WORKFLOW.md` (core graph; still valid)
- [x] `docs/RAG.md`
- [x] `docs/INTEGRATIONS.md`
- [x] `docs/API.md`
- [x] `docs/SECURITY.md`
- [x] `docs/IMPLEMENTATION_PLAN.md`

**Exit:** Another engineer can implement phase 2 without inventing tenancy rules.

---

## Phase 2 — Identity schema and migrations

Status: implemented (`002_identity_and_tenancy`, identity models, workspace FKs).

**Files:** `backend/app/models/identity.py`, `backend/app/models/entities.py` (FK columns), `backend/alembic/versions/002_identity_and_tenancy.py`, tests for model constraints.

**Produces:** Tables in [DATABASE.md](DATABASE.md). Existing incidents backfilled to a single development org only if rows exist; new installs create tenants through register.

**Exit:** `alembic upgrade head` on empty Postgres creates identity + incident tables. `pytest` for migration smoke.

---

## Phase 3 — Backend foundation (gap fill)

Settings for JWT secret, token TTL, `OPSPILOT_ENV`, `OPSPILOT_INTEGRATION_MODE`. Structured logging with `request_id`. Ready probe. Dependency-injected `AppContext` gains `auth` services. Do not delete the workflow.

**Exit:** App boots with new settings; old incident tests still construct a workspace in fixtures.

---

## Phase 4 — Authentication and RBAC

Status: implemented (register/login/refresh/logout/me/workspace switch, ingest API keys, JWT on console routes). Historical corpus seed is disabled until phase 23.

Register, login, refresh, logout, me, workspace switch. Argon2 hashes. RBAC dependencies. Remove `X-Operator` as identity. Tests: register isolation (user A cannot read user B incidents), weak password rejected, revoked refresh rejected.

**Exit:** Unauthenticated `/incidents` is 401. Register + login returns a token that lists zero incidents in a new workspace.

---

## Phases 5–12

Wire the existing console to login. Scope ingest, SSE, graph context, tools, RAG, approvals, and execution to `workspace_id`. Keep node order. Add tests that two workspaces with the same service name do not leak knowledge or incidents.

**Exit of phase 12:** Approve still requires a DB row lock; execution still refuses unapproved HIGH tools.

---

## Phases 13–20

Complete real HTTP adapters with timeouts; keep mocks. RCA, inspector, audit actor ids, eval runner, admin settings (members, API keys), security headers, pytest/frontend tests.

---

## Phases 21–22

Docker Compose requires JWT secret. Production notes: migrations, secrets, no `AUTH_DISABLED`, Postgres SSL, reverse proxy for SSE.

---

## Phases 23–25 (do not start early)

Idempotent seeder for an Acme-style **operations** workspace (payments, cache, platform incidents — not a support chatbot). Landing page. Scripted LinkedIn path: ingest → watch inspector → approve rollback → RCA.

---

## Definition of done for the product (not for a single phase)

- `pytest` passes without a vendor API key.
- Two registered users cannot see each other’s incidents.
- HIGH rollback cannot execute without `POST /approvals/{id}/approve` by an operator.
- Mock vs real adapters are explicit; real mode never reports mock success.
- README describes auth and the investigation workflow, and does not claim SSO or billing work until they do.
