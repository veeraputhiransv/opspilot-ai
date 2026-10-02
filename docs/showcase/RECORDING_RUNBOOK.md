# Recording runbook

Reset before every take. Do not reuse a leftover INC-1024.

## First-time setup

```bash
export OPSPILOT_DEMO_SEED_ENABLED=true
export OPSPILOT_DATABASE_URL="${OPSPILOT_DATABASE_URL:-postgresql+asyncpg://opspilot:opspilot@localhost:5432/opspilot}"
export OPSPILOT_REDIS_URL="${OPSPILOT_REDIS_URL:-redis://localhost:6379/0}"

# Postgres + Redis if they are not already up
docker compose up -d postgres redis

# API + console (Compose or local uvicorn/next)
# Console: http://localhost:3000
# Do not show .env, tokens, or the terminal in the recording.

python scripts/seed_demo.py
```

## Before every recording attempt

```bash
export OPSPILOT_DEMO_SEED_ENABLED=true
python scripts/reset_demo.py
```

Expected: live hero incidents removed, leftover knowledge docs removed, historical incidents kept, counter back at INC-1024.

## Browser

1. New window, 1440 × 900 or 1440 × 1000, bookmarks and DevTools hidden.
2. Open `http://localhost:3000`.
3. Click **Try Demo** (do not type the demo password on camera).
4. Confirm dashboard: **AcmeFlow Production**, **Alex Morgan**, **No active incidents.**
5. Confirm **INC-0087** is in Recent incidents (Payment Service Connection Pool Exhaustion).
6. Optional: Integrations page shows **Simulation** badges. Do not linger there.
7. Record from the dashboard. Script: [DEMO_SCRIPT.md](DEMO_SCRIPT.md). Captions: [VIDEO_CAPTIONS.md](VIDEO_CAPTIONS.md).

If a take fails or you approve by accident:

```bash
python scripts/reset_demo.py
```

Start over from the dashboard. Do not continue a dirty session.

## After the take

Export 1080p 16:9, 60–90 seconds. Upload to LinkedIn (or another stable host). Do not commit the raw video. Add the public URL to the README only after it exists.
