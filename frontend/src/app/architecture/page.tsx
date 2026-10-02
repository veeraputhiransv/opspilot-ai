"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function ArchitecturePage() {
  return (
    <main className="mx-auto min-h-screen max-w-4xl px-6 py-12">
      <p className="text-sm font-semibold tracking-wide">OpsPilot AI</p>
      <h1 className="mt-3 text-3xl font-semibold">Architecture</h1>
      <p className="mt-3 text-sm leading-7 text-muted">
        A modular monolith. The browser never decides incident state. FastAPI persists every
        investigation step. Policy code, not the model, classifies risk.
      </p>
      <pre className="mt-8 overflow-x-auto rounded-md border border-line bg-surface p-5 text-xs leading-6 text-muted">
        {`Browser → Next.js console
        → FastAPI
           ├─ Auth / RBAC
           ├─ Event ingestion
           ├─ LangGraph investigation
           ├─ Policy engine
           ├─ Tool layer → Integration resolver
           │                 ├─ GitHub
           │                 ├─ Slack
           │                 ├─ Email
           │                 ├─ Logs
           │                 └─ Deployment provider
           ├─ Human approval
           ├─ PostgreSQL + pgvector
           └─ Redis pub/sub`}
      </pre>
      <h2 className="mt-10 text-xl font-medium">Agent workflow</h2>
      <pre className="mt-4 overflow-x-auto rounded-md border border-line bg-surface p-5 text-xs leading-6 text-muted">
        {`Event → Triage → Logs → Deployments → Source control
     → Historical search → Hypothesis → Plan → Risk policy
     → Human approval → Execution → RCA`}
      </pre>
      <h2 className="mt-10 text-xl font-medium">Safety model</h2>
      <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-muted">
        <li>The reasoner proposes hypotheses and actions from evidence.</li>
        <li>Policy code assigns risk and whether approval is required.</li>
        <li>A human approves high-risk actions as a Postgres row.</li>
        <li>Tools execute through adapters. Demo adapters are labeled Simulation.</li>
      </ul>
      <div className="mt-10 flex gap-3">
        <Button asChild>
          <Link href="/">Back to product</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/login">Sign in</Link>
        </Button>
      </div>
    </main>
  );
}
