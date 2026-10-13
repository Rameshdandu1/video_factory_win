from __future__ import annotations

import json

import pytest

from video_app.application.assets import MediaInspectionError
from video_app.infrastructure.media import parse_ffprobe


def test_parses_rational_video_and_audio_metadata() -> None:
    payload = json.dumps(
        {
            "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "1.501"},
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1280,
                    "height": 720,
                    "avg_frame_rate": "30000/1001",
                },
                {"codec_type": "audio", "sample_rate": "48000", "channels": 2},
            ],
        }
    ).encode()

    metadata = parse_ffprobe(payload)

    assert metadata.duration_ms == 1501
    assert (metadata.frame_rate_numerator, metadata.frame_rate_denominator) == (30000, 1001)
    assert metadata.sample_count == 72_048


@pytest.mark.parametrize(
    "payload",
    [b"not json", b"{}", b'{"format":{"format_name":"wav","duration":"0"},"streams":[]}'],
)
def test_rejects_invalid_or_empty_probe_results(payload: bytes) -> None:
    with pytest.raises(MediaInspectionError):
        parse_ffprobe(payload)
