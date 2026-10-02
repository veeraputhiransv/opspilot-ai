# Screenshot set

Capture from the seeded AcmeFlow workspace. Hide bookmarks, developer tools, and localhost badges.

| # | Shot | File | How |
| --- | --- | --- | --- |
| 1 | Dashboard | `docs/screenshots/01-dashboard.png` | Demo session, AcmeFlow Production, empty live queue |
| 2 | Live investigation | `docs/screenshots/02-live-investigation.png` | Hero incident timeline + AI Investigation |
| 3 | Evidence | `docs/screenshots/03-evidence-correlation.png` | Primary hypothesis and supporting evidence |
| 4 | Human approval | `docs/screenshots/04-human-approval.png` | HIGH `rollback_deployment` card before Approve |
| 5 | Execution | `docs/screenshots/05-execution.png` | Approved/executed rollback |
| 6 | RCA | `docs/screenshots/06-rca.png` | Resolved incident RCA |
| 7 | Agent run inspector | `docs/screenshots/07-agent-run.png` | `/agent-runs` graph steps |
| — | Architecture | `docs/screenshots/architecture.svg` | Committed diagram |

Capture after a demo reset so leftover incidents cannot leak into RAG:

```bash
export OPSPILOT_DEMO_SEED_ENABLED=true
python scripts/seed_demo.py
python scripts/reset_demo.py
CAPTURE_SCREENSHOTS=1 bash scripts/run-e2e.sh e2e/capture-screenshots.spec.ts
```

The capture spec resets again, waits on persisted incident state, and targets the `rollback_deployment` card only.
