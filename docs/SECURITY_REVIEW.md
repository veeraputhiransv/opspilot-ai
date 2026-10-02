# Security review (hardening milestone)

Reviewed against the repository after phases 19–36. This is not a claim of zero vulnerabilities.

## Fixed in this milestone

- Workspace secrets encrypted at rest (AES-GCM); API output is metadata-only
- SSE no longer accepts reusable JWTs in query strings; short-lived stream tickets only
- Distributed Redis rate limits with in-memory fallback and `Retry-After`
- Provider HTTP restricted to HTTPS allowlisted hosts (SSRF control)
- GitHub repository allowlist enforced in the adapter, not the model
- Action execution uses `execution_id` plus EXECUTING to block duplicate side effects
- RAG and incident GET remain workspace-scoped; isolation tests cover ingest, tickets, and integrations
- Prompt-like log text is flagged; it cannot register tools or skip policy

## Accepted risk

- Stream tickets are reusable until TTL/max uses so EventSource can reconnect without minting a JWT
- In-process worker: a crash mid-EXECUTING may require operator retry; destructive tools are `DO_NOT_RETRY`
- Demo adapters still supply investigation fixtures when `OPSPILOT_MODE=demo`
- Derived vault key in development if `OPSPILOT_VAULT_MASTER_KEY` is unset
- CORS is origin-allowlisted; the console uses bearer tokens, not cookies (CSRF surface is low)

## Future hardening

- Dedicated KMS envelope keys per tenant
- Redis AUTH/TLS and ticket store HA
- Refresh-token reuse detection alerts
- Browser E2E in every environment including preview apps
- WAF / IP allowlists in front of ingest
- Signed Slack/GitHub webhook inbound requests
