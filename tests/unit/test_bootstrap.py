from __future__ import annotations

import sys
import unittest
from collections.abc import Coroutine
from typing import Any, NoReturn
from unittest.mock import patch

from video_app.bootstrap import worker_main


def _raise_keyboard_interrupt(coroutine: Coroutine[Any, Any, None]) -> NoReturn:
    coroutine.close()
    raise KeyboardInterrupt


def _raise_runtime_error(coroutine: Coroutine[Any, Any, None]) -> NoReturn:
    coroutine.close()
    raise RuntimeError("worker startup failed")


class WorkerMainTests(unittest.TestCase):
    def test_operator_interrupt_exits_without_propagating(self) -> None:
        with (
            patch.object(sys, "argv", ["video-app-worker", "--env-file", "ignored.env"]),
            patch("video_app.bootstrap._settings_from_file"),
            patch("video_app.bootstrap.asyncio.run", side_effect=_raise_keyboard_interrupt),
        ):
            worker_main()

    def test_unexpected_runtime_error_still_propagates(self) -> None:
        with (
            patch.object(sys, "argv", ["video-app-worker", "--env-file", "ignored.env"]),
            patch("video_app.bootstrap._settings_from_file"),
            patch("video_app.bootstrap.asyncio.run", side_effect=_raise_runtime_error),
            self.assertRaisesRegex(RuntimeError, "worker startup failed"),
        ):
            worker_main()


if __name__ == "__main__":
    unittest.main()
