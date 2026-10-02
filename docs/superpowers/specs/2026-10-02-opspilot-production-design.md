# OpsPilot AI production design

Date: 2026-10-02

## Decision

**Approach B — modular monolith with workspace tenancy.** Approaches A (current demo-open single tenant) and C (microservices) are rejected. See [ARCHITECTURE.md](../../ARCHITECTURE.md).

## Product

OpsPilot AI is an incident response and operations platform. Core path: event → triage → investigation → correlation → hypothesis → plan → policy → human approval → execution → resolution → RCA.

Not in scope as the product: customer-support copilot, free-form chat tool loop.

## Auth

Demo workspace (option A from product discussion) is **phase 23**. Primary path is email/password. SSO tables exist from the identity migration.

## Evolution

Keep LangGraph, policy engine, typed tools, pgvector, SSE. Add identity and `workspace_id` everywhere operational data is stored.
