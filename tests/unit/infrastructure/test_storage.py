from __future__ import annotations

import hashlib
import tempfile
import unittest
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

from video_app.application.assets import AssetTooLargeError, InvalidAssetError
from video_app.domain.models import BackendOutput, Resolution
from video_app.infrastructure.storage import LocalArtifactStore

NOW = datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)


async def _chunks(*items: bytes) -> AsyncIterator[bytes]:
    for item in items:
        yield item


class LocalArtifactStoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.storage_temp = tempfile.TemporaryDirectory()
        self.candidate_temp = tempfile.TemporaryDirectory()
        self.root = Path(self.storage_temp.name).resolve()
        self.store = LocalArtifactStore(self.root)

    def tearDown(self) -> None:
        self.storage_temp.cleanup()
        self.candidate_temp.cleanup()

    def candidate(self, payload: bytes | None = None) -> BackendOutput:
        content = payload or b"\x00\x00\x00\x18ftypisomplaceholder"
        path = Path(self.candidate_temp.name).resolve() / "candidate.mp4"
        path.write_bytes(content)
        return BackendOutput(path, Resolution(832, 480), 81, None)

    async def test_stores_hashes_and_consumes_candidate(self) -> None:
        output = self.candidate()
        payload = output.temporary_path.read_bytes()
        result = await self.store.store("job-1", output, NOW)

        stored = self.store.resolve_for_read(result.storage_key)
        self.assertFalse(output.temporary_path.exists())
        self.assertEqual(stored.read_bytes(), payload)
        self.assertEqual(result.sha256, hashlib.sha256(payload).hexdigest())
        self.assertEqual(result.size_bytes, len(payload))
        self.assertEqual(list(self.root.glob("*.part")), [])

    async def test_delete_is_idempotent_and_rejects_untrusted_key(self) -> None:
        result = await self.store.store("job-1", self.candidate(), NOW)
        await self.store.delete(result.storage_key)
        await self.store.delete(result.storage_key)
        self.assertFalse((self.root / result.storage_key).exists())

        with self.assertRaises(ValueError):
            await self.store.delete("../outside.mp4")

    async def test_rejects_non_mp4_without_modifying_candidate(self) -> None:
        output = self.candidate(b"not-an-mp4")
        with self.assertRaisesRegex(ValueError, "MP4"):
            await self.store.store("job-1", output, NOW)
        self.assertTrue(output.temporary_path.exists())
        self.assertEqual(list(self.root.glob("*.part")), [])

    async def test_discard_candidate_is_idempotent(self) -> None:
        output = self.candidate()
        await self.store.discard_candidate(output)
        await self.store.discard_candidate(output)
        self.assertFalse(output.temporary_path.exists())

    def test_requires_existing_absolute_root(self) -> None:
        with self.assertRaises(ValueError):
            LocalArtifactStore(Path("relative"))

    async def test_upload_inspects_magic_hashes_and_uses_opaque_key(self) -> None:
        payload = b"RIFF\x04\x00\x00\x00WAVEdata"
        result = await self.store.store_upload(
            filename="voice.wav",
            declared_media_type="audio/wav",
            chunks=_chunks(payload[:5], payload[5:]),
            max_bytes=1024,
        )

        self.assertEqual(result.filename, "voice.wav")
        self.assertEqual(result.sha256, hashlib.sha256(payload).hexdigest())
        self.assertEqual(self.store.resolve_for_read(result.storage_key).read_bytes(), payload)
        self.assertNotIn("voice", result.storage_key)

    async def test_upload_rejects_spoofed_traversal_and_oversize_content(self) -> None:
        with self.assertRaises(InvalidAssetError):
            await self.store.store_upload(
                filename="../voice.wav",
                declared_media_type="audio/wav",
                chunks=_chunks(b"RIFFxxxxWAVE"),
                max_bytes=1024,
            )
        with self.assertRaises(InvalidAssetError):
            await self.store.store_upload(
                filename="voice.wav",
                declared_media_type="audio/wav",
                chunks=_chunks(b"not wave data"),
                max_bytes=1024,
            )
        with self.assertRaises(AssetTooLargeError):
            await self.store.store_upload(
                filename="voice.wav",
                declared_media_type="audio/wav",
                chunks=_chunks(b"RIFFxxxxWAVEtoolarge"),
                max_bytes=12,
            )
        self.assertEqual(list((self.root / "uploads").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
