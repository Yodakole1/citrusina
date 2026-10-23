from citrusina import platform_linux, settings


def test_defaults_and_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert settings.load() == settings.DEFAULTS
    prefs = {**settings.DEFAULTS, "trigger": "alt", "bubble_pos": [10, 20]}
    settings.save(prefs)
    assert settings.load() == prefs


def test_junk_settings_fall_back(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    settings.path().parent.mkdir(parents=True)
    settings.path().write_text('{"trigger": "hyper", "unknown": 1}')
    assert settings.load() == settings.DEFAULTS
    settings.path().write_text("not json")
    assert settings.load() == settings.DEFAULTS


def test_autostart(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    platform_linux.set_autostart(True)
    text = platform_linux.autostart_file().read_text()
    assert "-m citrusina --background" in text
    platform_linux.set_autostart(False)
    assert not platform_linux.autostart_file().exists()


def test_session(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert platform_linux.session() == "wayland" and not platform_linux.global_input()
    monkeypatch.delenv("WAYLAND_DISPLAY")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setenv("DISPLAY", ":0")
    assert platform_linux.global_input()


def test_rings_follow_the_chosen_order():
    prefs = settings.load()
    items = ["md", "html", "pdf", "json", "py"]
    assert settings.arrange(prefs, "convert", "text", items) == items
    settings.remember(prefs, "convert", "text", ["json", "pdf", "md"], ["md"])
    # chosen ones first, the hidden one gone, the rest keep their usual order
    assert settings.arrange(prefs, "convert", "text", items) == ["json", "pdf", "html", "py"]
    assert settings.layout(prefs, "convert", "text", items) == [
        ("json", True), ("pdf", True), ("md", False), ("html", True), ("py", True)]
    settings.forget(prefs, "convert", "text")
    assert settings.arrange(prefs, "convert", "text", items) == items


def test_ring_choices_survive_a_save(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    prefs = settings.load()
    settings.remember(prefs, "tools", "image", ["crop"], ["redact"])
    settings.save(prefs)
    assert settings.load()["rings"]["tools"]["image"] == {"order": ["crop"], "hidden": ["redact"]}
    settings.path().write_text('{"rings": {"convert": {"text": {"order": "nope", "hidden": [1, "md"]}}}}')
    assert settings.load()["rings"]["convert"]["text"] == {"order": [], "hidden": ["md"]}
