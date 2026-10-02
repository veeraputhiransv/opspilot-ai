# OpsPilot AI — Integrations

The LLM never calls GitHub, Slack, Gmail, calendars, or deploy systems. The tool registry asks for a **capability** such as `source.recent_commits`. `IntegrationService` selects the workspace adapter that advertises that capability. Vendor names are not hard-coded in the agent graph.

Workspace credentials live in the secret vault (`integration_connections.encrypted_credentials`). Process environment variables may still hold the vault master key and default infrastructure URLs.

## Modes

`OPSPILOT_INTEGRATION_MODE=mock|real` (replaces the overloaded idea that “demo” means “no auth”).

- **mock:** adapters return fixture data and simulated side effects. Results are still persisted as real `tool_call` rows. The UI does not invent them.
- **real:** adapters use HTTP with timeouts. Missing configuration **fails the tool**. It does not silently succeed.

A LinkedIn seed (phase 23) may use mock adapters. That is an adapter choice, not a fake API.

## Adapter protocol

Each capability is a protocol, for example `LogSearch`, `DeploymentHistory`, `CommitSearch`, `IssueTracker`, `ChatNotifier`, `MailSender`, `ChangeExecutor` (rollback/restart via webhook only).

Factory: `build_integrations(settings) -> IntegrationBundle`. Tools depend on the bundle, not on `httpx` directly.

## Timeouts and safety

Every HTTP call has connect and read timeouts. Rollback and restart are webhooks (`OPSPILOT_ROLLBACK_WEBHOOK`, `OPSPILOT_RESTART_WEBHOOK`), never SSH, never a shell. Repos, channels, mail groups, and rollback versions are allowlists enforced in policy, not in the prompt.

## n8n (optional)

n8n is an **optional** outbound webhook adapter for teams that already orchestrate Slack/GitHub there. It is not the conversation engine, not the policy engine, and not required to run OpsPilot. If used, FastAPI signs the webhook secret and treats the JSON response as a tool result.

## GitHub / Slack / email

Real adapters land in the integrations phase. Until credentials exist, mock adapters keep the graph testable. Settings UI shows **readiness** (configured / missing), never secret values.
