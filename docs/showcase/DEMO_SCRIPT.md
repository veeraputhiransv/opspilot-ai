# Demo recording script (60–90 seconds)

Pacing is in the recording, not the backend. Do not change `OPSPILOT_STEP_DELAY_MS` for the take. Reset first: [RECORDING_RUNBOOK.md](RECORDING_RUNBOOK.md).

Voiceover: about 75 seconds. Captions: [VIDEO_CAPTIONS.md](VIDEO_CAPTIONS.md).

## 0–5s — Hook

| | |
| --- | --- |
| Screen | Dashboard |
| Action | Hold on AcmeFlow Production. Then click **Run Incident Scenario**. |
| Visible | Workspace **AcmeFlow Production**, Alex Morgan, empty active queue, historical activity including INC-0087 |
| Caption | *What if AI could investigate a production incident — but not blindly execute dangerous actions?* |
| Voiceover | I wanted to explore a simple question: what should happen when an AI agent can investigate a real production incident, but shouldn't be trusted to blindly execute high-risk actions? |

## 5–12s — Production event

| | |
| --- | --- |
| Screen | Scenario modal, then the new incident |
| Action | Select **Payment API degradation**. Click **Trigger Incident**. |
| Visible | **INC-1024**, **Payment API Error Rate Spike**, payment-service / production, **SEV-1** |
| Caption | *A production payment incident fires.* / Production incident detected |
| Voiceover | This is OpsPilot AI. A payment-service incident just fired. OpsPilot starts investigating automatically. |

## 12–28s — Investigation

| | |
| --- | --- |
| Screen | Incident timeline + AI Investigation |
| Action | Slow scroll through the timeline. Do not hunt. |
| Visible | Logs analyzed; deploy **v2.8.1**; commit **f39a812** `refactor: tune payment database connection pool`; historical **INC-0087** |
| Caption | *OpsPilot correlates logs, deployments, source control, and incident history.* |
| Voiceover | It correlates application logs, the latest deployment, a recent Git commit, and similar historical incidents. |

## 28–38s — Root cause

| | |
| --- | --- |
| Screen | Primary hypothesis |
| Action | Pause on the score and evidence. Do not call the score a probability. |
| Visible | **Database connection pool exhaustion after v2.8.1 deployment**, Investigation score, supporting evidence, INC-0087 |
| Caption | *Evidence-backed root cause — not just an LLM guess.* |
| Voiceover | Here it identifies database connection-pool exhaustion as the primary hypothesis and shows the supporting evidence. |

## 38–53s — Human approval

| | |
| --- | --- |
| Screen | Rollback approval card only |
| Action | Pause 3–5 seconds. Then click **Approve rollback**. |
| Visible | **Human Approval Required**, **Rollback payment-service from v2.8.1 to v2.8.0**, **HIGH**, PENDING APPROVAL |
| Caption | *The model proposes. Policy code decides the risk. A human approves production changes.* |
| Voiceover | The agent recommends rolling the service back — but this is a production mutation, so deterministic policy marks it high risk and pauses the workflow. I approve the rollback. |

## 53–65s — Execution

| | |
| --- | --- |
| Screen | Execution panel |
| Action | Stay on the rollback row while status moves to executed. Ignore a pending GitHub issue if it appears. |
| Visible | Rollback **EXECUTED** (or executing → executed), tool `rollback_deployment` |
| Caption | *Approved action executes through the controlled tool layer.* |
| Voiceover | The same persisted workflow resumes and executes the action idempotently. |

## 65–80s — Resolution and RCA

| | |
| --- | --- |
| Screen | Hero status, then RCA |
| Action | Scroll RCA: Root Cause, Resolution, Preventive Actions, Evidence. |
| Visible | **Resolved**, then grounded RCA sections |
| Caption | *The incident resolves and OpsPilot generates a grounded RCA automatically.* |
| Voiceover | It tracks recovery, resolves the incident, and writes the RCA from persisted facts. |

## 80–90s — Close

Prefer **Agent runs** if the latest run shows the graph steps. Use `/architecture` only if that frame is cleaner.

| | |
| --- | --- |
| Action | Cut to the inspector or architecture page. Hold the last line. |
| Caption | *LangGraph · FastAPI · Next.js · PostgreSQL/pgvector · Redis · RAG · HITL · Policy-as-Code* |
| End card | **OpsPilot AI — Detect. Investigate. Explain. Approve. Resolve.** |
| Voiceover | Under the hood: LangGraph, FastAPI, Next.js, PostgreSQL with pgvector, Redis, RAG, human-in-the-loop approvals, tool policy, observability, and multi-tenant isolation. |

## Full voiceover (~75s)

I wanted to explore a simple question: what should happen when an AI agent can investigate a real production incident, but shouldn't be trusted to blindly execute high-risk actions?

This is OpsPilot AI.

A payment-service incident just fired. OpsPilot starts investigating automatically.

It correlates application logs, the latest deployment, a recent Git commit, and similar historical incidents.

Here it identifies database connection-pool exhaustion as the primary hypothesis and shows the supporting evidence.

The agent recommends rolling the service back — but this is a production mutation, so deterministic policy marks it high risk and pauses the workflow.

I approve the rollback.

The same persisted workflow resumes, executes the action idempotently, tracks recovery, resolves the incident, and generates the RCA.

Under the hood this uses LangGraph, FastAPI, Next.js, PostgreSQL with pgvector, Redis, RAG, human-in-the-loop approvals, tool policies, observability, and multi-tenant isolation.
