# Roadmap

OpsPilot’s investigation graph, policy engine, tenancy, and approval path are implemented. These items are next, not implied as already shipped.

## Near term

- Queue worker (`OPSPILOT_WORKER_MODE=queue`) in front of the same LangGraph
- Hosted embeddings behind the existing `Embedder` protocol (same vector dimension)
- OpenTelemetry export for traces and tool latency
- Refresh-token reuse detection alerts

## Later

- OIDC login UI on top of existing `identity_providers` / `user_identities` tables
- Dedicated KMS envelope keys per tenant
- Redis AUTH/TLS and highly available ticket store
- Signed Slack/GitHub inbound webhooks
- WAF / IP allowlists in front of ingest

## Out of scope for v1

- Automatic promotion of a Slack draft into a send
- Billing
- Microservice split of ingest, policy, and workers
- A free-form tool-calling chat loop
