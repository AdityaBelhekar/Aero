"""`aero brain` CLI surface — hermetic (tmp AERO_HOME, keyring faked)."""

from __future__ import annotations

from aero import settings as st
from aero.cli import build_parser, cmd_brain
from aero.config import Config


def _run(cfg, argv):
    args = build_parser().parse_args(["brain", *argv])
    return cmd_brain(cfg, args)


def test_status_runs(tmp_path, capsys):
    assert _run(Config(home=tmp_path), []) == 0
    out = capsys.readouterr().out
    assert "Active brain: local" in out
    assert "litellm" in out  # registry listed


def test_set_switches_profile(tmp_path):
    cfg = Config(home=tmp_path)
    _run(cfg, ["--set", "groq"])
    assert st.load(cfg).brain_profile == "groq"


def test_set_two_speed(tmp_path):
    cfg = Config(home=tmp_path)
    _run(cfg, ["--primary", "groq", "--reflex", "local"])
    s = st.load(cfg)
    assert s.primary_profile == "groq" and s.reflex_profile == "local"


def test_private_only_toggle(tmp_path):
    cfg = Config(home=tmp_path)
    _run(cfg, ["--private-only"])
    assert st.load(cfg).brain_private_only is True
    _run(cfg, ["--shared"])
    assert st.load(cfg).brain_private_only is False


def test_model_override_writes_custom_profile(tmp_path):
    cfg = Config(home=tmp_path)
    _run(cfg, ["--set", "openai", "--model", "gpt-4o"])
    s = st.load(cfg)
    assert s.brains.get("openai", {}).get("model") == "gpt-4o"
    # and it takes effect through the registry
    assert st.resolve_brain_profile(s).model == "gpt-4o"


def test_set_key_via_keyring(tmp_path, monkeypatch, capsys):
    from aero.cognition import keys

    class FakeKeyring:
        def __init__(self): self.store = {}
        def get_password(self, s, n): return self.store.get(n)
        def set_password(self, s, n, v): self.store[n] = v
        def delete_password(self, s, n): self.store.pop(n, None)

    fake = FakeKeyring()
    monkeypatch.setattr(keys, "_keyring", lambda: fake)
    _run(Config(home=tmp_path), ["--set-key", "groq", "gk-secret"])
    assert "keyring" in capsys.readouterr().out.lower()
    assert fake.store["groq"] == "gk-secret"


def test_set_key_without_backend_reports(tmp_path, monkeypatch, capsys):
    from aero.cognition import keys
    monkeypatch.setattr(keys, "_keyring", lambda: None)
    _run(Config(home=tmp_path), ["--set-key", "groq", "x"])
    assert "No keyring backend" in capsys.readouterr().out
