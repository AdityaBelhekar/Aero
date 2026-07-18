"""Voice engine catalog + registry (AERO-VOX-401/402). Hermetic."""

from __future__ import annotations

from aero.voice.catalog import (
    BUILTIN_VOICE,
    VoiceProfile,
    catalog,
    registry,
)


def test_builtins_cover_existing_engines():
    reg = registry()
    for pid in ("kokoro", "svara", "parler", "sapi",
                "whisper-small", "moonshine", "indic"):
        assert pid in reg


def test_roles_are_correct():
    reg = registry()
    assert reg["kokoro"].role == "tts"
    assert reg["whisper-small"].role == "stt"


def test_local_engines_are_private_and_keyless():
    for p in catalog(implemented_only=True):
        if p.local:
            assert p.private and p.key_env is None


def test_cloud_engines_need_keys():
    reg = registry()
    assert reg["elevenlabs"].key_env == "ELEVENLABS_API_KEY"
    assert not reg["elevenlabs"].local


def test_catalog_filters_by_role():
    tts = catalog("tts")
    stt = catalog("stt")
    assert all(p.role == "tts" for p in tts)
    assert all(p.role == "stt" for p in stt)
    assert {p.id for p in tts} & {p.id for p in stt} == set()


def test_cloud_engines_now_implemented():
    # the cloud adapters are built now -> all catalogued engines are selectable
    built_tts = {p.id for p in catalog("tts", implemented_only=True)}
    built_stt = {p.id for p in catalog("stt", implemented_only=True)}
    assert {"elevenlabs", "sarvam_tts", "cartesia", "kokoro"} <= built_tts
    assert {"deepgram", "sarvam_stt", "whisper-small"} <= built_stt


def test_custom_profile_overrides_builtin():
    reg = registry({"kokoro": {"default_model": "am_adam"}})
    assert reg["kokoro"].default_model == "am_adam"
    assert reg["kokoro"].local is True           # rest inherited


def test_custom_new_engine():
    reg = registry({"myttts": {"role": "tts", "backend": "custom",
                               "key_env": "MY_KEY"}})
    assert reg["myttts"].role == "tts"
    assert reg["myttts"].implemented is True      # default


def test_registry_does_not_mutate_builtins():
    registry({"kokoro": {"default_model": "changed"}})
    assert BUILTIN_VOICE["kokoro"].default_model == "am_michael"


def test_streaming_flag_present_on_streaming_engines():
    reg = registry()
    assert reg["moonshine"].streaming is True
    assert reg["elevenlabs"].streaming is True
    assert reg["whisper-small"].streaming is False


def test_profile_frozen():
    p = VoiceProfile(id="x", role="tts", backend="b")
    try:
        p.id = "y"  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("VoiceProfile should be frozen")
