# LinkedIn assets (do not publish automatically)

## Project title

OpsPilot AI — incident investigation with human-controlled remediation

## One-line hook

What happens when an AI agent can investigate a production incident—but cannot roll back without a human?

## GitHub description

Authenticated multi-tenant incident response: LangGraph investigation, evidence correlation, deterministic policy, HITL approval, and Playwright-proven E2E.

## GitHub topics

`incident-response` `langgraph` `fastapi` `nextjs` `postgresql` `redis` `rag` `human-in-the-loop` `observability` `playwright`

## Short post

I built OpsPilot AI to answer a specific engineering question: can an agent investigate a real production incident without being trusted to execute dangerous actions?

It ingests an alert, correlates logs, deploys, commits, and prior incidents, then pauses a HIGH-risk rollback until a human approves. The approval is a Postgres row. The UI cannot fake it.

Repo stays private until the final review. Demo video coming next.

## Detailed post

Most AI agent demos skip the hard part.

Either the investigation is scripted theater, or the agent is allowed to call production tools with too much trust.

OpsPilot AI is an incident-response control plane:

Detect → Investigate → Explain → Approve → Resolve

A payment-service error-rate spike becomes a persisted incident. LangGraph collects logs, the deploy 43 seconds earlier, commit `f39a812`, and historical incident INC-0087. Policy code marks rollback HIGH. A human named Alex Morgan approves. The adapter executes. RCA is written.

The interesting engineering is not “an agent that talks.” It is:

- multi-tenant workspace isolation
- RAG over prior incidents
- deterministic risk policy
- human approval as data
- idempotent execution
- workflow recovery
- agent observability without hidden chain-of-thought
- Playwright E2E on GitHub-hosted runners

This is a portfolio system, not a claim of an enterprise SaaS rollout.

## Technology list

Next.js, TypeScript, FastAPI, SQLAlchemy, Alembic, LangGraph, PostgreSQL, pgvector, Redis, SSE, Docker, GitHub Actions, pytest, Playwright
