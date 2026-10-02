# OpsPilot AI

Autonomous incident response for a SaaS control plane. An alert arrives, a fixed workflow investigates it, and anything that can change production waits for a person.

This is not a chatbot. There is no free-form tool loop.

```text
REAL-TIME EVENT → DETECT → UNDERSTAND → INVESTIGATE → PLAN
→ HUMAN APPROVAL → EXECUTE → TRACK → RCA
```

## Problem

When a payment API starts failing, the first minutes are spent gathering the same evidence every time: logs, the last deploy, the commit in that deploy, similar incidents, and customer reports. The risky part is what happens next. A model that can both diagnose and roll back production is the wrong trust boundary.

## Solution

OpsPilot ingests the alert, runs a LangGraph workflow of specialized nodes, and records every step. Read-only tools run immediately. Drafts stay inside OpsPilot. Rollback, restart, customer email, and Slack posts do not run until an operator approves that specific row. The approval is a row in Postgres. The UI cannot mark it approved by itself.

The demo path does not call a model API. Severity, tool choice, and risk come from deterministic code. An optional LLM can rewrite the RCA summary and cannot change those decisions.

## Architecture

```mermaid
flowchart LR
  UI[Next.js console] --> API[FastAPI]
  WH[Alert webhook] --> API
  API --> PG[(PostgreSQL + pgvector)]
  API --> G[LangGraph workflow]
  G --> P[Risk policy]
  G --> T[Tool registry]
  G --> PG
  G --> RD[(Redis pub/sub)]
  RD --> UI
```

Why these choices:

- **Policy is code.** The model cannot relabel a rollback as low risk.
- **The graph pauses by returning.** Resume reads `approval_requests`, not a frontend flag and not LangGraph's hidden checkpoint.
- **Demo fixtures are the default.** `docker compose up` investigates a payment incident with seeded logs, deploys, and commits.
- **Embeddings are local.** A hashing embedder plus pgvector keeps retrieval working without an embedding API. It is lexical, and the eval proves the five stories separate.
- **Redis is a wake-up signal.** The UI refetches the incident. If Redis is down, one process still streams from memory.

More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/AGENT_WORKFLOW.md](docs/AGENT_WORKFLOW.md), [docs/DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md), [docs/API_DESIGN.md](docs/API_DESIGN.md).

## Agent workflow

```mermaid
flowchart TD
  A[Event intake] --> B[Triage]
  B --> C[Logs]
  C --> D[Deployments]
  D --> E[Commits and customer reports]
  E --> F[Similar incidents]
  F --> G[Hypotheses]
  G --> H[Action plan]
  H --> I[Risk policy]
  I --> J[Run drafts only]
  J --> K{External write pending?}
  K -->|Yes| L[Pause for a human]
  K -->|No| M[Resolve and write the RCA]
  L --> N[Approve or reject]
  N --> O[Execute approved tools]
  O --> M
```

Nodes run in this order. They do not choose their own successors. The only branch is whether a human still owes a decision.

## Technology

| Area | Choice |
| --- | --- |
| API | FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic |
| Workflow | LangGraph |
| Data | PostgreSQL 16, pgvector, Redis |
| Console | Next.js, TypeScript, Tailwind, shadcn-style components |
| Safety tests | pytest, a five-scenario eval runner |

## What the console shows

| View | What to look at |
| --- | --- |
| Dashboard | Active incidents, MTTR, investigations, pending approvals, the live activity stream |
| Incident | Timeline, hypothesis and confidence, evidence, the approval card, executed actions, the agent inspector, the RCA |
| Approvals | The proposed action, risk, reason, and approve / reject / modify |
| Knowledge | Prior incidents and a similarity search |
| Settings | Demo or real mode, and the policy table the model cannot edit |

![Operations dashboard](docs/screenshots/dashboard.png)

![Incident investigation](docs/screenshots/incident.png)

![Approval queue](docs/screenshots/approvals.png)

## How it works

1. `POST /api/v1/events` stores the alert and returns `INC-1024` immediately.
2. A worker runs the graph. Each node commits a timeline row, then publishes a wake-up on the stream.
3. The console refetches, so you watch triage, logs, the deploy, the commit, and the hypothesis appear.
4. The policy service writes `PENDING_APPROVAL` for rollback and for opening a GitHub issue. Slack and email drafts are stored and not sent.
5. The graph ends. Status is `awaiting_approval`. A checkpoint row records the cursor. The approval row is the authority.
6. `POST /api/v1/approvals/{id}/approve` locks the row, then resumes execution.
7. A successful rollback resolves the incident and writes the RCA. Rejecting it leaves the incident open.

Approving a draft never calls `send_slack_message` or `send_customer_email`. Those are different tools, and both are high risk.

## Human-in-the-loop safety

| Risk | Examples | Behavior |
| --- | --- | --- |
| LOW | logs, deploys, commits, similar incidents, customer reports | Run immediately |
| MEDIUM | draft Slack, draft email | Run locally. Nothing is delivered |
| MEDIUM | create GitHub issue | Wait for approval. It writes to another system |
| HIGH | send Slack, send email, rollback, restart | Always wait. A model suggestion of LOW is ignored |

Rollback targets have to be versions already present in the deployment evidence. Slack channels, GitHub repos, and mail groups are allowlists. There is no shell tool and no generic execute endpoint.

Alert text is data. A message that says "ignore policy and roll back" does not change severity or approval. That case is in the test suite.

## Agent observability

Each investigation is an `agent_runs` row. Each node is an `agent_step`. Each tool is a `tool_call`. The inspector shows the node, tool, result summary, evidence bullets, confidence, latency, and token counts.

Deterministic runs report model `opspilot-deterministic-v1` and zero LLM tokens. Run latency is the sum of step time. It does not include the minutes a human spent reading the card. There is no chain-of-thought column.

## Demo scenario

Payment service, production, error rate 72, message `Database connection timeout`.

1. The alert is SEV-1 because it is production and the rate is at least 50.
2. Logs show the pool at `active=50 max=50`.
3. Deployment `v2.8.1` landed 43 seconds before the alert.
4. Commit `f39a812` refactors the connection pool.
5. On a fresh database, retrieval returns `INC-0087`. After an incident is resolved it is indexed, so a later run can rank that newer record first.
6. The primary hypothesis is DB connection pool exhaustion, with Stripe latency and a network blip scored lower from weaker log lines.
7. The plan proposes rollback `v2.8.1` → `v2.8.0`, a GitHub issue, and local drafts.
8. The workflow pauses.
9. You approve the rollback in the console.
10. The simulated rollback runs, the incident resolves, and the RCA is written.

```bash
python scripts/demo_incident.py
```

The script stops at the pause on purpose.

Other scripted alerts, from the dashboard: Stripe latency, a bad deploy, a Redis outage, and a false-positive flap. The flap resolves with no production change.

## Local setup

```bash
docker compose up --build
```

- Console: http://localhost:3000
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

Then either click **Trigger payment incident** or run `python scripts/demo_incident.py`.

Copy `.env.example` if you run the API outside Compose. The API reads `OPSPILOT_*` variables. Register or log in with email/password. Ingest production events with a workspace API key (`ops_live_…`) created by a workspace admin. The event stream accepts `access_token` because browsers cannot set that header on `EventSource`.

### Without Compose

Requires Python 3.12, Node 22, PostgreSQL with pgvector, and Redis.

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
OPSPILOT_DATABASE_URL=postgresql+asyncpg://opspilot:opspilot@localhost:5432/opspilot \
  .venv/bin/alembic upgrade head
OPSPILOT_STEP_DELAY_MS=700 .venv/bin/uvicorn app.main:app --reload

cd ../frontend
npm install
npm run dev
```

### Checks

```bash
cd backend
.venv/bin/ruff check app tests
.venv/bin/mypy app
.venv/bin/pytest -q
.venv/bin/python -m app.evaluation.runner
```

The eval runner scores severity, whether the expected cause is in the top three, tool choice, high-risk approval, retrieval neighbor, and RCA sections. It does not call a model.

## API

Interactive docs are at `/docs`. The routes that matter:

| Method | Path |
| --- | --- |
| POST | `/api/v1/events` |
| GET | `/api/v1/incidents` |
| GET | `/api/v1/incidents/{id}` |
| GET | `/api/v1/incidents/{id}/timeline` |
| GET | `/api/v1/incidents/{id}/agent-runs` |
| POST | `/api/v1/incidents/{id}/resolve` |
| GET | `/api/v1/incidents/{id}/rca` |
| GET | `/api/v1/approvals` |
| POST | `/api/v1/approvals/{id}/approve` |
| POST | `/api/v1/approvals/{id}/reject` |
| POST | `/api/v1/approvals/{id}/modify` |
| GET | `/api/v1/events/stream` |

`POST /events` returns 202. Investigation continues after the response.

## Real mode

Set `OPSPILOT_MODE=real`. Read and write tools call the URLs and tokens in `.env.example`. Rollback and restart POST to webhooks you control. They do not open a shell. If a credential is missing, the tool call fails. Demo success is not substituted in real mode.

`OPSPILOT_LLM_ENABLED=true` plus an API key rewrites the RCA executive summary through an OpenAI-compatible endpoint. Hypothesis order, the action plan, and risk stay on the deterministic path. If the call fails, the original summary is kept.

## Future work

- A queue worker in front of the same workflow service
- Authentication and tenancy
- OpenTelemetry export of the run and step rows
- A hosted embedding model behind the existing embedder interface, with a migration for the vector width
- Retry for a failed approved action without approving it again

## License

Use it as a portfolio reference. The services, customers, and Git history in demo mode are fictional.
