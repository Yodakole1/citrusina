"""What we can convert from and to, and how to find it.

The lists follow what Tangerine offers on the Mac. A format can be read
without being writable (svg, rar), so inputs and outputs are kept apart.
"""
from functools import lru_cache
from pathlib import Path

# plain text in all its costumes. Most of these just change the name, which is the point:
# a note that should be a script, a log you want as markdown
TEXT = ["txt", "md", "html", "json", "csv", "yaml", "xml", "py", "js", "ts", "sh", "css",
        "c", "cpp", "h", "java", "rs", "go", "toml", "ini", "log"]

KINDS = {
    "image": {
        "in": ["jpg", "png", "heic", "webp", "tiff", "bmp", "svg", "gif"],
        "out": ["jpg", "png", "heic", "webp", "tiff", "bmp", "gif", "pdf"],
    },
    "video": {
        "in": ["mp4", "mov", "mkv", "avi", "wmv", "webm"],
        "out": ["mp4", "mov", "mkv", "avi", "wmv", "webm"],
    },
    "audio": {
        "in": ["mp3", "m4a", "wav", "flac", "ogg", "opus", "aiff"],
        "out": ["mp3", "m4a", "wav", "flac", "ogg", "opus", "aiff"],
    },
    "text": {
        "in": TEXT,
        "out": ["txt", "md", "html", "pdf", "docx", *TEXT[3:]],
    },
    "document": {
        "in": ["pdf", "docx"],
        "out": ["pdf", "docx", "txt", "md"],
    },
    "subtitle": {
        "in": ["srt", "vtt"],
        "out": ["srt", "vtt"],
    },
    "archive": {
        "in": ["zip", "tar", "tar.gz", "rar"],
        "out": ["zip", "tar", "tar.gz"],
    },
}

# other spellings of something we already list
ALIASES = {"jpeg": "jpg", "tif": "tiff", "heif": "heic", "tgz": "tar.gz",
           "aif": "aiff", "oga": "ogg", "markdown": "md", "htm": "html", "yml": "yaml",
           "text": "txt"}

KNOWN = {e for io in KINDS.values() for e in io["in"]}

# only for typing in the search box: people say gzip, but a lone .gz is not a tar
QUERY_ALIASES = {"gzip": "tar.gz", "gz": "tar.gz"}


def normalize(ext):
    ext = ext.lower().lstrip(".")
    return ALIASES.get(ext, ext)


def ext_of(path):
    """The extension we care about, which for tarballs is two parts.

    A file whose name doesn't say (tmp, README, notes.conf) is judged by what's inside.
    """
    name = Path(path).name.lower()
    if name.endswith(".tar.gz"):
        return "tar.gz"
    ext = normalize(Path(name).suffix)
    if ext not in KNOWN:
        try:
            st = Path(path).stat()
        except OSError:
            return ext
        return _sniffed(str(path), st.st_mtime_ns, st.st_size) or ext
    return ext


# what a file starts with, for the formats that say so
MAGIC = [
    (0, b"\x89PNG", "png"), (0, b"\xff\xd8\xff", "jpg"), (0, b"GIF8", "gif"),
    (0, b"%PDF", "pdf"), (0, b"PK\x03\x04", "zip"), (0, b"Rar!", "rar"),
    (0, b"fLaC", "flac"), (0, b"OggS", "ogg"), (0, b"ID3", "mp3"), (0, b"\xff\xfb", "mp3"),
    (0, b"\x1a\x45\xdf\xa3", "mkv"), (8, b"WEBP", "webp"), (8, b"WAVE", "wav"),
    (8, b"AVI ", "avi"), (8, b"AIFF", "aiff"), (4, b"ftypheic", "heic"), (4, b"ftypM4A", "m4a"),
    (4, b"ftypqt", "mov"), (4, b"ftyp", "mp4"), (0, b"II*\x00", "tiff"), (0, b"MM\x00*", "tiff"),
    (257, b"ustar", "tar"),
]


@lru_cache(maxsize=256)
def _sniffed(path, _mtime, _size):
    try:
        with open(path, "rb") as f:
            head = f.read(8192)
    except OSError:
        return None
    for offset, magic, ext in MAGIC:
        if head[offset:offset + len(magic)] == magic:
            return ext
    if head.startswith(b"\x1f\x8b"):
        return None     # gzip, but we can't tell a tarball from a lone .gz without unpacking
    return "txt" if looks_like_text(head) else None


def looks_like_text(head):
    if not head:
        return True     # an empty file can be any text you like
    if b"\x00" in head:
        return head[:2] in (b"\xff\xfe", b"\xfe\xff")    # utf-16 has zeros
    try:
        # the sample can end halfway through a character
        head.decode("utf-8")
        return True
    except UnicodeDecodeError as e:
        if e.start >= len(head) - 3:
            return True
    # old 8-bit text: almost everything printable
    printable = sum(32 <= b < 127 or b in b"\t\r\n" or b >= 160 for b in head)
    return printable / len(head) > 0.95


def kind_of(path):
    ext = ext_of(path)
    for kind, io in KINDS.items():
        if ext in io["in"]:
            return kind
    return None


def base_name(path):
    """File name without the extension, so photo.tar.gz gives photo."""
    name = Path(path).name
    if name.lower().endswith(".tar.gz"):
        return name[:-7]
    # ext_of may have normalized jpeg to jpg, so don't measure the suffix from it
    return Path(name).stem


def targets_for(path):
    """Formats worth offering for this file, never its own."""
    kind = kind_of(path)
    if kind is None:
        return []
    own = ext_of(path)
    return [e for e in KINDS[kind]["out"] if e != own]


def search(query, targets):
    """Prefix matches first, then anything that contains the text."""
    q = query.strip().lower().lstrip(".")
    q = QUERY_ALIASES.get(q, normalize(q))
    if not q:
        return list(targets)
    starts = [t for t in targets if t.startswith(q)]
    inside = [t for t in targets if q in t and t not in starts]
    return starts + inside
