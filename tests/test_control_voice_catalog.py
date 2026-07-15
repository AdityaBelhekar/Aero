"""voice.catalog control op (AERO-VOX-402). Hermetic."""

from __future__ import annotations

from aero.config import Config
from aero.control import ControlService


def test_voice_catalog_op(tmp_path):
    r = ControlService(Config(home=tmp_path)).dispatch("voice.catalog")
    assert r["ok"]
    cat = r["result"]
    tts_ids = {e["id"] for e in cat["tts"]}
    stt_ids = {e["id"] for e in cat["stt"]}
    assert {"kokoro", "svara", "elevenlabs"} <= tts_ids
    assert {"whisper-small", "moonshine"} <= stt_ids
    # default active TTS = sapi
    assert any(e["active"] and e["id"] == "sapi" for e in cat["tts"])


def test_voice_catalog_local_ready_cloud_needs_key(tmp_path, monkeypatch):
    from aero.cognition import keys
    monkeypatch.setattr(keys, "_keyring", lambda: None)
    for e in ("ELEVENLABS_API_KEY", "SARVAM_API_KEY", "CARTESIA_API_KEY"):
        monkeypatch.delenv(e, raising=False)
    cat = ControlService(Config(home=tmp_path)).dispatch("voice.catalog")["result"]
    by_id = {e["id"]: e for e in cat["tts"]}
    assert by_id["kokoro"]["key_set"] is True      # local -> ready
    assert by_id["elevenlabs"]["key_set"] is False  # cloud, no key
    assert by_id["elevenlabs"]["implemented"] is False


def test_voice_catalog_reflects_selection(tmp_path):
    from aero import settings as st
    cfg = Config(home=tmp_path)
    s = st.load(cfg); s.engine = "kokoro"; st.save(s, cfg)
    cat = ControlService(cfg).dispatch("voice.catalog")["result"]
    assert any(e["active"] and e["id"] == "kokoro" for e in cat["tts"])
