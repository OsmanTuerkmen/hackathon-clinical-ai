import json
import os
import re
import subprocess
import urllib.error
from pathlib import Path

import pytest

from tools import voiceover
from tools.voiceover import (
    DemoRow,
    VoiceClip,
    cached_voice_clip,
    cache_key,
    load_demo_rows,
    main,
    mix_audio,
    tempo_for_slot,
)


ROOT = Path(__file__).resolve().parents[1]


def test_dry_run_reports_demo_rows_slots_and_estimated_credits(capsys):
    assert main(["--dry-run"]) == 0
    output = capsys.readouterr().out

    assert "0:00–0:12" in output
    assert "1:54–2:00" in output
    assert "Rows: 12" in output
    assert "Estimated credits:" in output


def test_demo_rows_match_the_subtitle_source_and_last_slot():
    rows = load_demo_rows(ROOT / "DEMO.md")

    assert len(rows) == 12
    assert rows[0].start == 0
    assert rows[0].end == 12
    assert rows[-1].start == 114
    assert rows[-1].end == 120
    assert rows[0].text.startswith("AccessDesk 2")
    assert not rows[0].text.startswith("„")
    assert not rows[0].text.endswith("“")


def test_cache_key_is_stable_and_sensitive_to_voice_settings():
    settings = {"stability": 0.45, "similarity": 0.8, "style": 0.15, "speaker_boost": True}

    first = cache_key("Sprechtext", "voice-a", "eleven_multilingual_v2", settings)
    reordered = cache_key(
        "Sprechtext",
        "voice-a",
        "eleven_multilingual_v2",
        {"speaker_boost": True, "style": 0.15, "similarity": 0.8, "stability": 0.45},
    )

    assert first == reordered
    assert first != cache_key("Sprechtext", "voice-b", "eleven_multilingual_v2", settings)
    assert len(first) == 16


def test_cached_voice_clip_does_not_request_the_same_text_twice(tmp_path, monkeypatch):
    calls = []

    def fake_request(url, key, method="GET", payload=None, accept="application/json"):
        calls.append((url, payload))
        return b"synthetic-mp3"

    monkeypatch.setattr(voiceover, "_request", fake_request)
    settings = {"stability": 0.45, "similarity_boost": 0.8, "style": 0.15, "use_speaker_boost": True}

    first = cached_voice_clip("Hallo", "voice-id", "eleven_multilingual_v2", settings, "key", tmp_path)
    second = cached_voice_clip("Hallo", "voice-id", "eleven_multilingual_v2", settings, "key", tmp_path)

    assert first == second
    assert first.read_bytes() == b"synthetic-mp3"
    assert len(calls) == 1


def test_elevenlabs_key_is_sent_only_in_the_header(monkeypatch):
    captured = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"fake-audio"

    def fake_urlopen(request, timeout):
        captured.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(voiceover.urllib.request, "urlopen", fake_urlopen)
    result = voiceover._request(
        "https://api.elevenlabs.io/v1/text-to-speech/voice",
        "not-a-real-key",
        method="POST",
        payload={"text": "hello"},
        accept="audio/mpeg",
    )

    request, timeout = captured[0]
    assert result == b"fake-audio"
    assert request.get_header("Xi-api-key") == "not-a-real-key"
    assert "not-a-real-key" not in request.full_url
    assert timeout == 30


@pytest.mark.parametrize(
    ("method", "permission"),
    [("GET", "Voices: Read"), ("POST", "Text to Speech: Access")],
)
def test_elevenlabs_permission_errors_name_required_access(monkeypatch, method, permission):
    def denied(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "forbidden", {}, None)

    monkeypatch.setattr(voiceover.urllib.request, "urlopen", denied)
    with pytest.raises(voiceover.VoiceoverError, match=permission):
        voiceover._request(
            "https://api.elevenlabs.io/v1/voices",
            "not-a-real-key",
            method=method,
            payload={"text": "hello"} if method == "POST" else None,
        )


def test_tempo_for_slot_only_speeds_up_within_the_cap():
    assert tempo_for_slot(9.0, 10.0) == 1.0
    assert tempo_for_slot(10.0, 10.0) == pytest.approx(10.0 / 9.7)
    with pytest.raises(ValueError, match="shorter text"):
        tempo_for_slot(10.8, 10.0)


def test_mix_audio_places_synthetic_clips_in_their_slots(tmp_path):
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    output = tmp_path / "mix.wav"
    for frequency, path in ((440, first), (880, second)):
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i",
                f"sine=frequency={frequency}:duration=0.25",
                "-c:a", "pcm_s16le", str(path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    mix_audio(
        [VoiceClip(first, 0.0), VoiceClip(second, 1.0)],
        output,
        duration=2.0,
    )
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert float(json.loads(probe.stdout)["format"]["duration"]) == pytest.approx(2.0, abs=0.05)

    def mean_volume(start):
        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-ss", str(start), "-t", "0.15", "-i", str(output),
                "-af", "volumedetect", "-f", "null", os.devnull,
            ],
            capture_output=True,
            text=True,
        )
        match = re.search(r"mean_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", result.stderr)
        assert match
        return match.group(1)

    assert mean_volume(0.05) != "-inf"
    assert float(mean_volume(0.5)) < -60
    assert mean_volume(1.05) != "-inf"
