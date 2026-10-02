# OpsPilot AI — Agent execution

This document is the production contract for investigation. Node order and pause/resume match [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md). This file adds reasoning providers, tool contracts, and lifecycle relative to tenancy.

## Lifecycle of one incident

1. Ingest authenticates a workspace API key or an operator JWT, writes `incident_events` + `incidents` in that workspace, publishes SSE, returns 202.
2. Worker starts (or resumes) the graph with `incident_id` only. Nodes load state from Postgres, not from the HTTP request.
3. Each node: run tools or reasoner → persist rows → timeline → SSE wake-up → next node.
4. Policy writes risk and approval rows. Execution runs only what policy allows.
5. If anything still needs a human, the graph **returns**. Checkpoint stores cursor. Approvals table is authority.
6. `POST /approvals/{id}/approve` by an `operator+` user row-locks, writes decision, resumes worker.
7. Execution records `tool_calls`. Mitigating success → resolve → RCA → index knowledge in the same workspace.

LangGraph’s built-in checkpointer is not used. Hiding approval inside framework memory would make the console, tests, and audit lie.

## Reasoning provider

```python
class ReasoningProvider(Protocol):
    name: str
    async def severity(self, event: TriageInput) -> SeverityResult: ...
    async def hypotheses(self, evidence: EvidenceBundle) -> list[Hypothesis]: ...
    async def plan(self, primary: Hypothesis) -> list[ProposedAction]: ...
    async def rca(self, incident: RcaInput) -> RcaSections: ...
```

Implementations:

- `DeterministicReasoner` — default. Signal weights in code. Required for CI.
- `HybridReasoner` — deterministic control plane; optional LLM rewrites narrative fields only.
- Future: OpenAI / Anthropic / Gemini / Ollama clients behind `LlmClient` with timeouts, token accounting, and no tool execution.

`LlmClient` is not allowed to call the tool registry.

## Tool registry

Tools have a name, Pydantic args (`extra=forbid`), risk declared in policy (not in the tool), and an async `execute(ctx, args)`. Context includes workspace_id, incident_id, integration bundle, and clock. The model emits structured `{name, arguments}` only for planner output that is then validated; it never receives HTTP clients.

## Human-in-the-loop

States the console shows are incident status plus approval status. There is no `AI_ACTIVE` chat state. The analogous flags are graph running vs paused vs executing vs resolved.

Low confidence does not auto-execute HIGH tools. It can add a timeline warning and still require approval.
