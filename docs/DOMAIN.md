# OpsPilot AI — Domain Design

## Product invariant

OpsPilot investigates **operational incidents**. A conversation widget may exist later as a *view* of an incident. It is not the product.

## Tenancy

| Concept | Meaning |
| --- | --- |
| **User** | A person with email/password (and later linked SSO identities). |
| **Organization** | The tenant: billing, SSO config, org-wide admins. |
| **Workspace** | The operational boundary. Incidents, knowledge, API keys, and integrations belong here. |

A user may belong to several organizations. Membership at org level does not automatically grant every workspace; workspace membership is explicit.

Roles:

| Role | Scope | Can |
| --- | --- | --- |
| `owner` | organization | All admin plus transfer ownership |
| `admin` | organization or workspace | Members, settings, API keys, integrations |
| `operator` | workspace | Ingest visibility, approve/reject/modify, resolve |
| `viewer` | workspace | Read incidents, RCA, inspector |
| `auditor` | workspace | Read plus audit log export; cannot approve |

Webhook ingest does not use these roles. It uses a workspace API key with `events:write`.

## Incident lifecycle

Statuses (unchanged meaning, now workspace-scoped):

| Status | Meaning |
| --- | --- |
| `investigating` | Graph is running or about to run |
| `awaiting_approval` | At least one required action waits on a human |
| `executing` | Approved tools are running |
| `resolved` | Mitigating success, false positive, or operator resolve with RCA |
| `closed` | Terminal after resolve; no further automatic work |

Severity: `SEV-1` … `SEV-4`, set by triage rules, not by the model claiming a lower severity to skip approval.

## Action and approval

An **action** is a planned tool invocation with arguments validated by a Pydantic schema.

Risk is assigned only by `RiskPolicyService`:

- `LOW` — read-only investigation tools; run immediately
- `MEDIUM` — local drafts may run; writes to external systems wait
- `HIGH` — rollback, restart, send Slack, send email; always wait

Approval states: `PENDING_APPROVAL`, `APPROVED`, `REJECTED`. Modify keeps pending and cannot change `tool_name`.

Draft vs send remains two tools. Approving `draft_slack_message` never calls `send_slack_message`.

## Agent run

One investigation attempt is an `agent_run`. Each graph node is an `agent_step`. Each registry invocation is a `tool_call`. These exist whether or not an LLM is used. Deterministic runs still produce inspector rows.

## Knowledge

Prior incidents and operational documents are workspace-scoped sources for retrieval. Retrieval injects evidence. It never executes tools.

## Audit

Every authz decision that changes state (login, key create, approve, reject, resolve, settings) writes an append-only audit row with `actor_user_id` or `actor_key_id`, action, resource, workspace, and redacted detail. Alert payloads are treated as data, never as instructions.
