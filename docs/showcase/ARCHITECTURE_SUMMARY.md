# Architecture summary

OpsPilot is a modular monolith.

The browser is a console. FastAPI is the control plane. PostgreSQL is the system of record. Redis is fan-out. LangGraph is a fixed investigation, not a free-form tool loop.

```text
Browser → Next.js → FastAPI
  Auth/RBAC
  Event ingestion
  LangGraph
  Policy engine
  Tool layer → Integration resolver
                 GitHub / Slack / Email / Logs / Deployments
  Human approval
  PostgreSQL + pgvector
  Redis
```

Safety split:

- LLM / reasoner proposes
- Policy code decides
- Human approves high-risk actions
- Tools execute

The AcmeFlow demo uses this same path. Simulation adapters are labeled. They are not presented as live vendor connections.
