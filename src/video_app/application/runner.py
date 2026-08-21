"""Single-concurrency polling loop for the independently deployed worker."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from video_app.application.recovery import RecoverExpiredLeases
from video_app.application.worker import ProcessNextJob


@dataclass(frozen=True, slots=True)
class WorkerRunner:
    process_next: ProcessNextJob
    recover_expired: RecoverExpiredLeases
    poll_interval_seconds: float

    def __post_init__(self) -> None:
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")

    async def run_once(self) -> bool:
        await self.recover_expired()
        return await self.process_next() is not None

    async def run_until_stopped(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            processed = await self.run_once()
            if processed:
                continue
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.poll_interval_seconds)
            except asyncio.TimeoutError:
                continue
