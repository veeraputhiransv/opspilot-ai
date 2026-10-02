#!/usr/bin/env python3
"""Reset live demo incidents while preserving AcmeFlow history and identity."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.db import create_engine, create_session_factory, session_scope  # noqa: E402
from app.seed.demo import reset_demo  # noqa: E402


async def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    try:
        async with session_scope(sessions) as session:
            result = await reset_demo(session, settings)
        print(
            f"Removed {result['removed_incidents']} live demo incident(s) "
            f"and {result.get('removed_knowledge_documents', 0)} leftover knowledge document(s). "
            "Historical records kept."
        )
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
