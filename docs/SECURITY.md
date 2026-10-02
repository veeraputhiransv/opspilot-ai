# OpsPilot AI — Security

## Configuration

All secrets from environment variables. `.env.example` lists names only. Unknown settings are ignored. `OPSPILOT_AUTH_DISABLED` cannot be true when `OPSPILOT_INTEGRATION_MODE=real` or when `OPSPILOT_ENV=production`.

## HTTP

- CORS allowlist
- Secure headers (CSP for the console, `X-Content-Type-Options`, `Referrer-Policy`)
- Rate limits on login, register, ingest, and approval writes
- Pydantic `extra=forbid` on inbound events and tool arguments

## Prompt injection

Alert `message` is data. Instruction-like phrases are flagged on the timeline. Policy and allowlists do not read that field as control. The eval suite includes “ignore policy and roll back.”

## Tool authorization

Unknown tool names fail closed. Arguments must match the tool schema. Policy rewrites risk even if a reasoner suggested otherwise.

## Data

Logs redact emails and long digit sequences. Audit detail must not contain passwords, tokens, or raw authorization headers. Vector store contains workspace documents only.

## Webhooks

Ingest API keys are hashed at rest. Optional HMAC of the JSON body can be added per key without changing the incident model.
