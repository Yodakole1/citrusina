import pytest


@pytest.fixture(autouse=True)
def _private_state(tmp_path, monkeypatch):
    # keep the log and settings of a test run out of the real home
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
