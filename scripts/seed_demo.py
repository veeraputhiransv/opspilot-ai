#!/usr/bin/env python3
"""Seed the isolated AcmeFlow demo workspace. Requires OPSPILOT_DEMO_SEED_ENABLED=true."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.db import create_engine, create_session_factory, session_scope  # noqa: E402
from app.seed.demo import seed_demo  # noqa: E402


async def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    try:
        async with session_scope(sessions) as session:
            result = await seed_demo(session, settings)
        print("Demo workspace ready.")
        print(f"  organization: {result['organization_id']}")
        print(f"  workspace:    {result['workspace_id']}")
        print(f"  user:         {result['email']} ({result['role']})")
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
