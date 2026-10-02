# LinkedIn and GitHub launch copy

Do not publish or change repository visibility from this file. Apply GitHub About/topics in the GitHub UI after the repo is public.

## GitHub About

**Description**

AI incident-response platform with evidence-driven investigation, LangGraph orchestration, deterministic risk policy, human approval, and resumable remediation workflows.

**Topics**

`ai-agents` `langgraph` `fastapi` `nextjs` `rag` `incident-response` `human-in-the-loop` `agentic-ai` `observability` `postgresql` `redis` `llm`

**Website**

Add only after a public demo URL exists.

## Final LinkedIn post

What happens when you let an AI agent investigate a production incident — but refuse to let it blindly execute dangerous actions?

That question is why I built OpsPilot AI.

Most agent demos either fake the investigation or let a model call production tools with too much trust. I wanted the opposite: a real, persisted incident workflow where the agent can investigate, and a human still owns dangerous mutations.

A payment-service error-rate spike becomes an incident in Postgres. LangGraph correlates logs, the latest deploy, a Git commit, and similar historical incidents via RAG. Deterministic policy — not the model — marks rollback HIGH. The graph pauses on a human approval row. After I approve, the same workflow resumes, executes idempotently, resolves the incident, and writes an RCA from stored facts.

The engineering I cared about:

- event-driven investigation, not a chatbot
- evidence correlation before a hypothesis
- policy-as-code for risk
- resumable HITL, not a hidden tool loop
- multi-tenant isolation, vaulted secrets, agent-run observability
- evaluation plus Playwright E2E on GitHub-hosted runners (approve, reject, isolation, demo path)

Stack: LangGraph, FastAPI, Next.js, PostgreSQL/pgvector, Redis.

What I learned: the hard part is not “call a model.” It is making investigation, approval, and execution the same durable path in tests as in the demo.

60–90s demo: [add the LinkedIn / video URL after upload]

GitHub: https://github.com/veeraputhiransv/opspilot-ai

If you have built agent workflows that have to pause for a human, I want the technical feedback — especially on policy boundaries and recovery.

## Title / hook (profile or repo)

OpsPilot AI — incident investigation with human-controlled remediation
