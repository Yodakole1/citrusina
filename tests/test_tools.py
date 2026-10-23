import shutil
import subprocess
import wave

import pytest

from citrusina import convert, tools

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="no ffmpeg")


def photo(w=200, h=100):
    # a gradient, so crops and edits change pixels in a way we can see
    img = Image.new("RGB", (w, h))
    img.putdata([(x * 255 // w, y * 255 // h, 90) for y in range(h) for x in range(w)])
    return img


def tool(kind, key):
    return next(t for t in tools.TOOLS[kind] if t.key == key)


def test_tools_depend_on_kind(tmp_path):
    assert [t.key for t in tools.tools_for("a.png")][:2] == ["compress", "metadata"]
    assert "snapshot" in [t.key for t in tools.tools_for("a.mp4")]
    assert "normalize" in [t.key for t in tools.tools_for("a.flac")]
    assert tools.tools_for("a.txt") == []


def test_crop_margins_and_aspect():
    assert tools.crop(photo(), left=10, right=10).size == (160, 100)
    assert tools.crop(photo(), aspect="1:1").size == (100, 100)
    assert tools.crop(photo(100, 200), aspect="16:9").size == (100, 56)


def test_crop_that_would_leave_nothing_is_ignored():
    assert tools.crop(photo(), left=60, right=60).size == (200, 100)


def test_redact_only_touches_its_box():
    src = photo()
    out = tools.redact(src, 25, 25, 50, 50, "black").convert("RGB")
    assert out.getpixel((100, 50)) == (0, 0, 0)
    assert out.getpixel((5, 5)) == src.getpixel((5, 5))


@pytest.mark.parametrize("style", ["black", "pixelate", "blur"])
def test_redact_styles_change_the_box(style):
    src = photo()
    out = tools.redact(src, 25, 25, 50, 50, style).convert("RGB")
    assert out.crop((50, 25, 150, 75)).tobytes() != src.crop((50, 25, 150, 75)).tobytes()


def test_edit_rotate_swaps_dimensions_and_flip_mirrors():
    assert tools.adjust(photo(), rotate="90").size == (100, 200)
    src = photo()
    flipped = tools.adjust(src, flip="horizontal")
    assert flipped.getpixel((0, 0)) == src.getpixel((199, 0))


def test_edit_brightness_moves_pixels_the_right_way():
    src = photo()
    assert sum(tools.adjust(src, brightness=50).getpixel((100, 50))) > sum(src.getpixel((100, 50)))
    assert sum(tools.adjust(src, brightness=-50).getpixel((100, 50))) < sum(src.getpixel((100, 50)))


def test_annotate_draws_something_and_empty_text_does_not():
    src = photo()
    assert tools.annotate(src, "hi").convert("RGB").tobytes() != src.tobytes()
    assert tools.annotate(src, "") is src


def test_add_background_grows_the_canvas_and_keeps_the_photo_in_the_middle():
    src = photo(200, 100)
    out = tools.add_background(src, padding=10, corners=0, shadow=0)
    assert out.size == (240, 140)
    assert out.convert("RGB").getpixel((120, 70)) == src.getpixel((100, 50))


def test_add_background_ratio():
    out = tools.add_background(photo(200, 100), ratio="1:1")
    assert out.width == out.height


def test_rounded_corners_let_the_background_show():
    src = Image.new("RGB", (100, 100), (255, 0, 0))
    out = tools.add_background(src, "white", padding=20, corners=30, shadow=0).convert("RGB")
    # the photo's own corner is cut away, so it isn't red there
    assert out.getpixel((20, 20)) != (255, 0, 0)
    assert out.getpixel((70, 70)) == (255, 0, 0)


def test_result_is_named_like_tangerine_and_never_overwrites(tmp_path):
    src = tmp_path / "Page 001.png"
    photo().save(src)
    first = tools.run(tool("image", "crop"), src, {"aspect": "1:1"})
    second = tools.run(tool("image", "crop"), src, {"aspect": "1:1"})
    assert first.name == "Page 001 Cropped.png"
    assert second.name == "Page 001 Cropped (1).png"
    assert Image.open(first).size == (100, 100)


def test_add_bg_always_gives_png(tmp_path):
    src = tmp_path / "a.jpg"
    photo().save(src)
    assert tools.run(tool("image", "add bg"), src).name == "a With Background.png"


def test_metadata_removes_exif_but_keeps_the_pixels(tmp_path):
    src = tmp_path / "a.jpg"
    exif = Image.Exif()
    exif[0x010F] = "SecretCamera"
    photo().save(src, exif=exif)
    assert Image.open(src).getexif().get(0x010F) == "SecretCamera"
    out = tools.run(tool("image", "metadata"), src)
    assert not Image.open(out).getexif()
    assert Image.open(out).size == (200, 100)


def test_compress_makes_a_noisy_jpg_smaller(tmp_path):
    import random
    random.seed(1)
    src = tmp_path / "noise.jpg"
    noisy = Image.new("RGB", (200, 200))
    noisy.putdata([tuple(random.randrange(256) for _ in range(3)) for _ in range(200 * 200)])
    noisy.save(src, quality=95)
    out = tools.run(tool("image", "compress"), src, {"quality": 30})
    assert out.stat().st_size < src.stat().st_size


def test_compress_png_still_opens(tmp_path):
    src = tmp_path / "a.png"
    photo().save(src)
    assert Image.open(tools.run(tool("image", "compress"), src, {"quality": 40})).size == (200, 100)


def test_preview_runs_the_tool_on_the_given_image():
    out = tools.preview(tool("image", "crop"), photo(), {"aspect": "1:1"})
    assert out.size == (100, 100)
    assert tools.preview(tool("image", "compress"), photo(), {}).size == (200, 100)


def test_atempo_chains_what_ffmpeg_cannot_do_in_one_step():
    assert tools.atempo(1.5) == "atempo=1.5"
    assert tools.atempo(4) == "atempo=2,atempo=2"
    assert tools.atempo(0.25) == "atempo=0.5,atempo=0.5"


def test_ffmpeg_tools_report_a_missing_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(convert.shutil, "which", lambda _: None)
    with pytest.raises(convert.ConvertError, match="ffmpeg"):
        tools.run(tool("audio", "normalize"), tmp_path / "a.mp3")
    assert not list(tmp_path.glob("*Normalized*"))


# real ffmpeg from here on

def make_clip(path, seconds=2):
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"testsrc=size=64x64:rate=10:duration={seconds}", "-f", "lavfi", "-i",
                    f"sine=frequency=440:duration={seconds}", "-shortest", str(path)], check=True)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    return float(out.stdout)


@needs_ffmpeg
def test_video_trim_speed_snapshot_compress(tmp_path):
    src = tmp_path / "clip.mp4"
    make_clip(src)
    trimmed = tools.run(tool("video", "trim"), src, {"start": "0", "end": "1"})
    assert 0.8 < duration(trimmed) < 1.3
    fast = tools.run(tool("video", "speed"), src, {"speed": "2"})
    assert duration(fast) < 1.3
    shot = tools.run(tool("video", "snapshot"), src, {"time": "1"})
    assert shot.suffix == ".png" and Image.open(shot).size == (64, 64)
    assert tools.run(tool("video", "compress"), src, {"crf": 35}).exists()


@needs_ffmpeg
def test_audio_normalize_trim_channels(tmp_path):
    src = tmp_path / "tone.wav"
    with wave.open(str(src), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x10\x00\x10" * 16000)
    assert tools.run(tool("audio", "normalize"), src).exists()
    assert 0.8 < duration(tools.run(tool("audio", "trim"), src, {"start": "0", "end": "1"})) < 1.3
    mono = tools.run(tool("audio", "channels"), src, {"mode": "mono"})
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=channels", "-of",
                            "default=nw=1:nk=1", str(mono)], capture_output=True, text=True)
    assert probe.stdout.strip() == "1"


def test_bad_seconds_never_reach_ffmpeg():
    for bad in ("abc", "-5", "1; rm"):
        with pytest.raises(convert.ConvertError):
            tools._seconds(bad)
    assert tools._seconds("") == "0" and tools._seconds("1.50") == "1.5"


@needs_ffmpeg
def test_speed_works_on_a_clip_without_sound(tmp_path):
    src = tmp_path / "silent.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=64x64:rate=10:duration=2", str(src)], check=True)
    assert duration(tools.run(tool("video", "speed"), src, {"speed": "2"})) < 1.3
