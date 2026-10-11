import importlib

import config


def reload_config():
    return importlib.reload(config)


def test_defaults(monkeypatch):
    monkeypatch.delenv("ASH_WAKE_THRESHOLD", raising=False)
    monkeypatch.delenv("ASH_WAKE_MODEL", raising=False)
    cfg = reload_config()
    assert cfg.WAKE_THRESHOLD == 0.5
    assert cfg.WAKE_MODEL_PATH.name == "hey_ash.onnx"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("ASH_WAKE_THRESHOLD", "0.7")
    monkeypatch.setenv("ASH_WAKE_MODEL", "/tmp/other.onnx")
    cfg = reload_config()
    assert cfg.WAKE_THRESHOLD == 0.7
    assert str(cfg.WAKE_MODEL_PATH) == "/tmp/other.onnx"
    monkeypatch.undo()
    reload_config()
