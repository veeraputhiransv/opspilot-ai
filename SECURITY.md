# Security

OpsPilot is an incident-response platform. High-risk actions require a human approval row. That is a product invariant, not a claim that the software is free of vulnerabilities.

## Supported versions

| Version | Supported |
| --- | --- |
| `main` | Yes — report issues against current `main` |
| Tagged releases | Best effort while the tag is documented |

There is no paid support contract. Fixes land on `main`.

## Reporting a vulnerability

Do **not** open a public GitHub issue for exploitable bugs.

Email the maintainer through the GitHub profile attached to this repository, or use GitHub’s **private vulnerability reporting** if it is enabled on the repo.

Please include:

- Affected revision (`git rev-parse HEAD` or a tag)
- Impact (auth bypass, cross-workspace read, policy skip, secret leak, RCE, etc.)
- Reproduction that does **not** target third-party infrastructure you do not own
- Whether you have a suggested fix

You should hear back within 7 days. If the report is valid, we will coordinate a fix and credit you if you want that.

## High-level architecture

- Secrets come from environment variables. `.env` is not committed.
- Console sessions use short-lived JWTs. Ingest uses hashed workspace API keys.
- SSE uses short-lived stream tickets, not reusable JWTs in query strings.
- Every incident, knowledge, and integration query is workspace-scoped.
- Workspace credentials are encrypted at rest (AES-256-GCM). API responses are metadata-only.
- Risk is assigned by policy code. Models cannot relabel tools or skip approval.
- Alert `message` text is evidence. Instruction-like phrases are flagged; they never authorize tools.
- Demo seed (`OPSPILOT_DEMO_SEED_ENABLED`) is off by default and must stay off in production.

Details: [docs/SECURITY.md](docs/SECURITY.md), [docs/AUTH.md](docs/AUTH.md), [docs/VAULT.md](docs/VAULT.md).

## Responsible disclosure

- Do not publish exploit details until a fix is available or you have waited a reasonable window (90 days).
- Do not access other people’s data, or production systems that are not yours.
- Automated scanning of a hosted instance you do not operate is not authorized.
- Local reproduction against `docker compose` or your own database is welcome.

## Known product limitations

These are accepted architectural limits, not a pentest report:

- v1 runs HTTP and the worker in one process. A crash mid-execution may require operator retry; destructive tools are marked do-not-retry.
- Stream tickets are reusable until TTL / max uses so EventSource can reconnect.
- Development may derive a vault key from `OPSPILOT_JWT_SECRET` if `OPSPILOT_VAULT_MASTER_KEY` is unset. Production refuses to boot without a dedicated key.
- Demo adapters supply investigation fixtures when demo mode is enabled.

See [ROADMAP.md](ROADMAP.md) for planned hardening (queue worker, KMS, OIDC).
