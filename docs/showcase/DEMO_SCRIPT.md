# Demo video script (60–90 seconds)

Do not add fake product functionality for recording. Local `OPSPILOT_STEP_DELAY_MS=700` is enough pacing.

## On-screen captions

0–5: A production incident just fired.
5–15: Trigger Payment API degradation.
15–30: Logs. Deploy v2.8.1. Commit f39a812. INC-0087.
30–40: Primary hypothesis: connection pool exhaustion.
40–50: HIGH-risk rollback proposed.
50–60: Approve rollback.
60–70: Rollback executing.
70–80: Incident resolved.
80–90: RCA + architecture.

## Spoken script

A production incident just fired in AcmeFlow.

I trigger the Payment API degradation scenario. This is a real ingest into Postgres, not a mocked screen.

OpsPilot classifies SEV-1 and starts investigation. Watch the timeline: payment logs, deploy v2.8.1 forty-three seconds earlier, commit f39a812 that tuned the connection pool, and historical incident INC-0087.

The investigation score is not a probability. It is evidence correlation.

Policy marks rollback HIGH. I approve. The adapter runs in simulation. Health recovers. RCA is written.

Humans stay in control of dangerous actions. The agent does the investigation.

## Recording checklist

- Dark theme
- Seeded AcmeFlow workspace
- No localhost debug overlays
- Browser bookmarks hidden
- Start from the dashboard greeting
