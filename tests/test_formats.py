from citrusina import formats


def test_kind_of():
    assert formats.kind_of("a/photo.JPG") == "image"
    assert formats.kind_of("song.flac") == "audio"
    assert formats.kind_of("movie.wmv") == "video"
    assert formats.kind_of("subs.vtt") == "subtitle"
    assert formats.kind_of("notes.txt") == "text"
    assert formats.kind_of("report.docx") == "document"
    assert formats.kind_of("thing.xyz") is None


def test_tangerine_lists_are_covered():
    img = formats.KINDS["image"]
    assert {"jpg", "png", "heic", "webp", "tiff", "bmp", "svg", "gif"} <= set(img["in"])
    assert "pdf" in img["out"]
    assert {"mp4", "mov", "mkv", "avi", "wmv", "webm"} == set(formats.KINDS["video"]["out"])
    assert {"mp3", "m4a", "wav", "flac", "ogg", "opus", "aiff"} == set(formats.KINDS["audio"]["out"])
    assert {"zip", "tar", "tar.gz"} <= set(formats.KINDS["archive"]["out"])


def test_tarball_is_one_extension():
    assert formats.ext_of("backup.tar.gz") == "tar.gz"
    assert formats.ext_of("backup.TGZ") == "tar.gz"
    assert formats.base_name("dir/backup.tar.gz") == "backup"
    assert formats.base_name("photo.png") == "photo"


def test_plain_gz_is_not_a_tarball():
    assert formats.kind_of("notes.txt.gz") is None


def test_svg_and_rar_are_read_only():
    assert "svg" not in formats.KINDS["image"]["out"]
    assert "rar" not in formats.KINDS["archive"]["out"]
    assert formats.kind_of("logo.svg") == "image"
    assert formats.kind_of("old.rar") == "archive"


def test_targets_skip_own_format_and_spellings():
    assert "png" not in formats.targets_for("x.png")
    assert "jpg" not in formats.targets_for("x.jpeg")
    assert "tar.gz" not in formats.targets_for("x.tgz")


def test_unknown_file_has_no_targets():
    assert formats.targets_for("archive.xyz") == []


def test_search_prefers_prefix():
    assert formats.search("m", ["wav", "mp3", "m4a", "mkv"]) == ["mp3", "m4a", "mkv"]
    assert formats.search("p", ["webp", "png", "mp3"]) == ["png", "webp", "mp3"]


def test_search_understands_what_people_type():
    assert formats.search("jpeg", ["png", "jpg"]) == ["jpg"]
    assert formats.search("gzip", ["zip", "tar", "tar.gz"]) == ["tar.gz"]


def test_empty_search_returns_everything():
    assert formats.search("", ["png", "jpg"]) == ["png", "jpg"]


def test_base_name_uses_the_real_suffix():
    assert formats.base_name("holiday.jpeg") == "holiday"
    assert formats.base_name("scan.TIF") == "scan"
    assert formats.base_name("pack.tgz") == "pack"
    assert formats.base_name("a.b.png") == "a.b"


def test_files_without_a_telling_name_are_judged_by_content(tmp_path):
    note = tmp_path / "tmp"
    note.write_text("just some words\n")
    assert formats.ext_of(note) == "txt" and formats.kind_of(note) == "text"
    assert "md" in formats.targets_for(note)
    conf = tmp_path / "app.conf"
    conf.write_text("key = välue\n")
    assert formats.kind_of(conf) == "text"
    png = tmp_path / "picture"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
    assert formats.ext_of(png) == "png"
    blob = tmp_path / "blob"
    blob.write_bytes(bytes(range(256)) * 4)
    assert formats.kind_of(blob) is None
    assert formats.kind_of(tmp_path / "missing") is None


def test_named_files_are_trusted_without_reading(tmp_path):
    fake = tmp_path / "song.mp3"
    fake.write_text("not really audio")
    assert formats.ext_of(fake) == "mp3"


def test_an_empty_file_is_text(tmp_path):
    empty = tmp_path / "tmp"
    empty.touch()
    assert formats.kind_of(empty) == "text"
