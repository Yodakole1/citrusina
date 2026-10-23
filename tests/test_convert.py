import json
import shutil
import subprocess
import tarfile
import wave
import zipfile

import pytest

from citrusina import convert

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="no ffmpeg")
needs_pandoc = pytest.mark.skipif(shutil.which("pandoc") is None, reason="no pandoc")
needs_7z = pytest.mark.skipif(shutil.which("7z") is None, reason="no 7z")


def test_output_path_next_to_source(tmp_path):
    assert convert.output_path(tmp_path / "a.png", "jpg") == tmp_path / "a.jpg"


def test_output_path_never_overwrites(tmp_path):
    (tmp_path / "a.jpg").touch()
    (tmp_path / "a (1).jpg").touch()
    assert convert.output_path(tmp_path / "a.png", ".JPG") == tmp_path / "a (2).jpg"


def test_output_path_for_tarball(tmp_path):
    assert convert.output_path(tmp_path / "x.tar.gz", "zip") == tmp_path / "x.zip"


def test_refuses_what_it_cannot_do(tmp_path):
    with pytest.raises(convert.ConvertError):
        convert.convert(tmp_path / "a.png", "mp3")
    with pytest.raises(convert.ConvertError):
        convert.convert(tmp_path / "a.xyz", "png")


def test_missing_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(convert.shutil, "which", lambda _: None)
    with pytest.raises(convert.ConvertError, match="ffmpeg"):
        convert.convert(tmp_path / "a.mp3", "wav")


def test_failed_run_leaves_nothing_behind(tmp_path, monkeypatch):
    src = tmp_path / "a.mp3"
    src.touch()
    monkeypatch.setattr(convert.shutil, "which", lambda _: "/usr/bin/ffmpeg")

    def fake_run(cmd, **_):
        (tmp_path / "a.wav").touch()
        return subprocess.CompletedProcess(cmd, 1, "", "bad input")

    monkeypatch.setattr(convert.subprocess, "run", fake_run)
    with pytest.raises(convert.ConvertError, match="bad input"):
        convert.convert(src, "wav")
    assert not (tmp_path / "a.wav").exists()


def test_documents_only_offer_routes_with_a_tool(tmp_path, monkeypatch):
    monkeypatch.setattr(convert, "which", lambda name: name if name == "pandoc" else None)
    txt = convert.targets_for(tmp_path / "a.txt")
    assert "docx" in txt and "pdf" not in txt
    assert convert.targets_for(tmp_path / "a.pdf") == []
    assert convert.targets_for(tmp_path / "a.docx") == ["txt", "md"]


def test_text_offers_the_classics_with_no_tools_at_all(tmp_path, monkeypatch):
    monkeypatch.setattr(convert, "which", lambda name: None)
    txt = convert.targets_for(tmp_path / "a.txt")
    assert {"md", "py", "json", "html", "sh"} <= set(txt)
    assert "txt" not in txt and "docx" not in txt
    assert txt[:2] == ["md", "html"]


def test_text_to_text_keeps_the_content(tmp_path):
    src = tmp_path / "script.txt"
    src.write_bytes("print('héllo')\r\n".encode())
    out = convert.convert(src, "py")
    assert out.name == "script.py"
    assert out.read_bytes() == src.read_bytes()


def test_old_windows_text_is_read(tmp_path):
    src = tmp_path / "old.txt"
    src.write_bytes("caf\xe9".encode("cp1252"))
    assert convert.convert(src, "md").read_text() == "café"


def test_csv_and_json(tmp_path):
    src = tmp_path / "t.csv"
    src.write_text("name,n\na,1\nb,2\n")
    data = json.loads(convert.convert(src, "json").read_text())
    assert data == [{"name": "a", "n": "1"}, {"name": "b", "n": "2"}]
    back = tmp_path / "u.json"
    back.write_text('[{"x": 1}, {"y": [1, 2]}]')
    assert convert.convert(back, "csv").read_text().splitlines() == ["x,y", "1,", ',"[1, 2]"']
    flat = tmp_path / "v.json"
    flat.write_text("[1, 2]")
    assert convert.convert(flat, "csv").read_text().split() == ["1", "2"]


def test_html_without_pandoc(tmp_path, monkeypatch):
    monkeypatch.setattr(convert, "which", lambda name: None)
    page = tmp_path / "p.html"
    page.write_text("<html><head><title>x</title><style>b{}</style></head><body><p>Hi</p><p>there</p></body></html>")
    assert convert.convert(page, "txt").read_text().split() == ["Hi", "there"]
    note = tmp_path / "n.txt"
    note.write_text("a < b")
    assert "<pre>a &lt; b</pre>" in convert.convert(note, "html").read_text()


# the tests below use real files and real tools

def make_png(path, color=(200, 30, 30, 255)):
    from PIL import Image
    Image.new("RGBA", (16, 16), color).save(path)


@pytest.mark.parametrize("ext", ["jpg", "webp", "tiff", "bmp", "gif", "pdf"])
def test_image_formats(tmp_path, ext):
    pytest.importorskip("PIL")
    src = tmp_path / "pic.png"
    make_png(src)
    out = convert.convert(src, ext)
    assert out.exists() and out.stat().st_size > 0


def test_transparent_png_goes_white_in_jpg(tmp_path):
    from PIL import Image
    src = tmp_path / "pic.png"
    make_png(src, (0, 0, 0, 0))
    out = convert.convert(src, "jpg")
    r, g, b = Image.open(out).convert("RGB").getpixel((4, 4))
    assert min(r, g, b) > 240


def test_heic_round_trip(tmp_path):
    pytest.importorskip("pillow_heif")
    src = tmp_path / "pic.png"
    make_png(src)
    heic = convert.convert(src, "heic")
    back = convert.convert(heic, "png")
    assert back.exists()


def test_svg_to_png(tmp_path):
    pytest.importorskip("cairosvg")
    src = tmp_path / "logo.svg"
    src.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">'
                   '<rect width="20" height="20" fill="orange"/></svg>')
    assert convert.convert(src, "png").exists()


def make_wav(path):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x10" * 8000)


@needs_ffmpeg
@pytest.mark.parametrize("ext", ["mp3", "m4a", "flac", "ogg", "opus", "aiff"])
def test_audio_formats(tmp_path, ext):
    src = tmp_path / "tone.wav"
    make_wav(src)
    out = convert.convert(src, ext)
    assert out.exists() and out.stat().st_size > 0


@needs_ffmpeg
def test_subtitles(tmp_path):
    src = tmp_path / "s.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:02,000\nhello\n")
    out = convert.convert(src, "vtt")
    assert out.read_text().startswith("WEBVTT")


@needs_ffmpeg
@pytest.mark.parametrize("ext", ["mp4", "mkv", "webm", "mov", "avi"])
def test_video_formats(tmp_path, ext):
    src = tmp_path / "clip.mkv"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=64x64:rate=5:duration=1", str(src)], check=True)
    if ext == "mkv":
        pytest.skip("same as source")
    assert convert.convert(src, ext).exists()


@needs_pandoc
def test_txt_to_docx_and_back(tmp_path):
    src = tmp_path / "note.txt"
    src.write_text("hello there\n")
    docx = convert.convert(src, "docx")
    src.unlink()
    back = convert.convert(docx, "txt")
    assert "hello there" in back.read_text()


def make_tree(root):
    (root / "sub").mkdir()
    (root / "a.txt").write_text("a")
    (root / "sub" / "b.txt").write_text("b")


def names(archive_path):
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path) as z:
            return {n.rstrip("/") for n in z.namelist()}
    with tarfile.open(archive_path) as t:
        return {n.rstrip("/") for n in t.getnames()}


def test_archive_round_trip(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    make_tree(tree)
    src = tmp_path / "pack.zip"
    with zipfile.ZipFile(src, "w") as z:
        z.write(tree / "a.txt", "a.txt")
        z.write(tree / "sub" / "b.txt", "sub/b.txt")

    tgz = convert.convert(src, "tar.gz")
    assert tgz.name == "pack.tar.gz"
    assert {"a.txt", "sub/b.txt"} <= names(tgz)

    tar = convert.convert(tgz, "tar")
    zipped = convert.convert(tar, "zip")
    assert {"a.txt", "sub", "sub/b.txt"} == names(zipped)


def test_archive_cannot_escape_its_folder(tmp_path):
    evil = tmp_path / "evil.tar"
    payload = tmp_path / "payload.txt"
    payload.write_text("x")
    with tarfile.open(evil, "w") as t:
        t.add(payload, "../escaped.txt")
    with pytest.raises(convert.ConvertError):
        convert.convert(evil, "zip")
    assert not (tmp_path.parent / "escaped.txt").exists()


@needs_7z
def test_rar_is_read_through_7z(tmp_path):
    # no rar writer exists here, so just check the missing-file path reports cleanly
    with pytest.raises(convert.ConvertError):
        convert.convert(tmp_path / "missing.rar", "zip")


def test_output_name_for_alias_extensions(tmp_path):
    assert convert.output_path(tmp_path / "holiday.jpeg", "png") == tmp_path / "holiday.png"
    assert convert.output_path(tmp_path / "pack.tgz", "zip") == tmp_path / "pack.zip"


def test_camera_rotation_is_applied_when_converting(tmp_path):
    from PIL import Image
    src = tmp_path / "phone.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # stored sideways, to be shown rotated
    Image.new("RGB", (40, 20), "red").save(src, exif=exif)
    assert Image.open(convert.convert(src, "png")).size == (20, 40)


def test_cmyk_converts_to_png(tmp_path):
    from PIL import Image
    src = tmp_path / "print.jpg"
    Image.new("CMYK", (8, 8), (0, 100, 100, 0)).save(src)
    assert convert.convert(src, "png").exists()


@needs_pandoc
def test_text_line_breaks_survive_docx(tmp_path):
    src = tmp_path / "poem.txt"
    src.write_text("one\ntwo\nthree\n")
    back = convert.convert(convert.convert(src, "docx"), "txt")
    assert back.read_text().split() == ["one", "two", "three"]
    assert len(back.read_text().strip().splitlines()) == 3


def test_a_text_file_with_no_extension_converts(tmp_path):
    src = tmp_path / "tmp"
    src.write_text("hello\n")
    out = convert.convert(src, "md")
    assert out.name == "tmp.md" and out.read_text() == "hello\n"
