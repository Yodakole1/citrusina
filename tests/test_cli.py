import json

from PIL import Image

from citrusina import cli


def test_targets_json(tmp_path, capsys):
    src = tmp_path / "a.png"
    Image.new("RGB", (10, 10)).save(src)
    assert cli.main(["--targets", str(src)]) == 0
    info = json.loads(capsys.readouterr().out)
    assert "jpg" in info["convert"] and "png" not in info["convert"]
    crop = next(t for t in info["tools"] if t["key"] == "crop")
    assert {p["key"] for p in crop["params"]} == {"aspect", "left", "top", "right", "bottom"}


def test_convert_and_tool_print_the_new_file(tmp_path, capsys):
    src = tmp_path / "a.png"
    Image.new("RGB", (40, 20)).save(src)
    assert cli.main(["--convert", str(src), "jpg"]) == 0
    assert capsys.readouterr().out.strip() == str(tmp_path / "a.jpg")
    assert cli.main(["--tool", str(src), "crop", "aspect=1:1"]) == 0
    assert Image.open(capsys.readouterr().out.strip()).size == (20, 20)


def test_errors_exit_nonzero_with_a_message(tmp_path, capsys):
    src = tmp_path / "a.png"
    Image.new("RGB", (4, 4)).save(src)
    assert cli.main(["--convert", str(src), "mp3"]) == 1
    assert cli.main(["--tool", str(src), "crop", "nope=1"]) == 1
    assert cli.main(["--tool", str(src), "crop", "left=abc"]) == 1
    assert cli.main(["--tool", str(src), "nothing"]) == 1
    assert cli.main(["--bogus"]) == 2
    assert "citrusina:" in capsys.readouterr().err


def test_cli_needs_no_qt(tmp_path, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "PySide6", None)
    src = tmp_path / "a.png"
    Image.new("RGB", (4, 4)).save(src)
    assert cli.main(["--targets", str(src)]) == 0
