"""Runs the workflow after the HTTP response is sent.

A separate queue consumer can call `IncidentWorkflow.start` later. The demo
keeps the task in-process so a recording does not depend on a broker.
"""

import asyncio
import logging
from uuid import UUID

from app.agents.workflow import IncidentWorkflow

logger = logging.getLogger("opspilot.worker")


class IncidentWorker:
    def __init__(self, workflow: IncidentWorkflow) -> None:
        self.workflow = workflow
        self._tasks: set[asyncio.Task] = set()

    def enqueue(self, incident_id: UUID) -> None:
        task = asyncio.create_task(self._run(incident_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        pending = set(self._tasks)
        if pending:
            await asyncio.wait(pending, timeout=8)

    async def _run(self, incident_id: UUID) -> None:
        try:
            await self.workflow.start(incident_id)
        except Exception:
            logger.exception("worker_failed incident=%s", incident_id)
