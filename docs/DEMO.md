# Demo

OpsPilot ships an optional **AcmeFlow** workspace so visitors can run a complete incident without registering an organization.

**AcmeFlow is fictional.** Simulation adapters return fixture evidence and simulated side effects. Results are persisted as real `tool_call`, approval, and RCA rows. They do not contact GitHub, Slack, email, or deploy systems.

Never enable demo seed in production.

## What the demo simulates

A payment API error-rate spike (`payment-service`, production, 72% errors, `Database connection timeout`).

The investigation graph:

1. Triages the event as SEV-1.
2. Correlates logs (connection pool exhausted), a recent deploy (`v2.8.1`), and a commit that refactors the pool.
3. Retrieves a prior workspace incident (`INC-0087`) as evidence, not as authorization.
4. Scores a primary hypothesis: database connection pool exhaustion.
5. Plans rollback, a GitHub issue, and local drafts.
6. Policy marks rollback **HIGH**. The graph pauses on a persisted approval row.
7. After a human approves `rollback_deployment`, execution, resolution, and RCA run on the same pipeline used by a registered workspace.

## Enable demo mode

Demo seed is off by default.

```bash
export OPSPILOT_DEMO_SEED_ENABLED=true
```

Optional (fictional, demo-only password):

```bash
export OPSPILOT_DEMO_PASSWORD=AcmeFlow-operator-12
```

Required services: PostgreSQL with pgvector, Redis, FastAPI, Next.js. Docker Compose is the simplest path:

```bash
docker compose up --build
```

The API must see `OPSPILOT_DEMO_SEED_ENABLED=true` (Compose local override or your `.env`).

## Seed

```bash
python scripts/seed_demo.py
```

Creates:

| Field | Value |
| --- | --- |
| Organization | AcmeFlow |
| Workspace | AcmeFlow Production |
| Operator | Alex Morgan (`alex.morgan@acmeflow.example`) |
| Role | Incident Commander (`operator`, not admin) |

Historical incidents and knowledge documents are seeded for retrieval. Seed is idempotent.

## Reset

```bash
python scripts/reset_demo.py
```

Removes in-flight hero incidents so you can run the payment scenario again. It does **not** delete the demo user, historical incidents, or knowledge.

## Start the application

If Compose is already running, open http://localhost:3000.

Without Compose:

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload

cd ../frontend
npm run dev
```

## Trigger the Payment API scenario

1. Open the console.
2. Click **Try Demo** (logs in as Alex Morgan in the AcmeFlow workspace).
3. Click **Run Incident Scenario**.
4. Wait until status is `awaiting_approval` and the rollback approval is visible.
5. Approve or reject `rollback_deployment` in the console.

CLI equivalent (API must already be running and seeded):

```bash
python scripts/demo_incident.py
python scripts/demo_incident.py http://localhost:8000
```

The script logs in as the demo operator, triggers `db_pool`, and waits until the workflow pauses. It does not approve anything.

## What you should expect to see

| Surface | Expect |
| --- | --- |
| Dashboard | AcmeFlow workspace, seeded history, **Run Incident Scenario** |
| Live investigation | Timeline, evidence, primary hypothesis, current activity |
| Approvals | Pending `rollback_deployment` (HIGH). Optional GitHub issue stays pending. |
| After approve | Execution, resolved status, RCA from persisted facts |
| After reject | Incident stays open; rollback is not executed |
| Integrations | Adapters labeled **Simulation** |

Draft Slack/email tools may run locally. Approving a draft never sends a real message.

## Screenshots

Product screenshots used in the README live in `docs/screenshots/`. To regenerate them:

```bash
CAPTURE_SCREENSHOTS=1 bash scripts/run-e2e.sh e2e/capture-screenshots.spec.ts
```
