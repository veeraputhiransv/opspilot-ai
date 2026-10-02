# Logs as evidence

Log lines retrieved during investigation are **evidence**, not instructions.

The investigation graph must not treat log `message` text as a tool call, policy override, or repository/channel/service selector.

`looks_like_injection` flags instruction-like phrases. Flagged lines remain visible to operators and are stored as evidence summaries. They never authorize `rollback_deployment` or any other tool. RiskPolicyService remains code.
