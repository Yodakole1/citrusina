import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

from citrusina import formats, text
from citrusina.formats import ext_of, normalize


class ConvertError(Exception):
    pass


# documents have no single tool, so each pair says which ones it needs
DOC_ROUTES = {
    ("pdf", "txt"): ("pdftotext",),
    ("pdf", "md"): ("pdftotext",),
    ("docx", "txt"): ("pandoc",),
    ("docx", "md"): ("pandoc",),
    ("docx", "pdf"): ("soffice",),
    ("txt", "docx"): ("pandoc",),
    ("md", "docx"): ("pandoc",),
    ("html", "docx"): ("pandoc",),
    ("txt", "pdf"): ("soffice",),
    ("html", "pdf"): ("soffice",),
    ("md", "pdf"): ("pandoc", "soffice"),
}
RICH = ("pdf", "docx")
# other names the same program goes by, the LibreOffice snap for one
ALSO_KNOWN_AS = {"soffice": ("libreoffice",)}


def which(name):
    """A program on PATH, or next to our own Python, which a venv or env may not have on PATH."""
    for candidate in (name, *ALSO_KNOWN_AS.get(name, ())):
        found = shutil.which(candidate) or shutil.which(candidate, path=str(Path(sys.executable).parent))
        if found:
            return found
    return None


def targets_for(path):
    """Like formats.targets_for, minus routes whose tool isn't installed."""
    src = ext_of(path)
    kind = formats.kind_of(path)
    targets = formats.targets_for(path)
    if kind not in ("document", "text"):
        return targets

    def possible(t):
        if kind == "text" and t not in RICH:
            return True     # text to text needs nothing
        tools = DOC_ROUTES.get((src, t))
        return tools is not None and all(which(n) for n in tools)
    return [t for t in targets if possible(t)]


def output_path(src, ext, suffix=None):
    """Next to the source, and never on top of an existing file.

    A suffix gives names like "photo Cropped.png", the way Tangerine names tool results.
    """
    src = Path(src)
    ext = normalize(ext)
    base = formats.base_name(src)
    if suffix:
        base = f"{base} {suffix}"
    out = src.with_name(f"{base}.{ext}")
    n = 1
    while out.exists():
        out = src.with_name(f"{base} ({n}).{ext}")
        n += 1
    return out


def _run(cmd):
    exe = which(cmd[0])
    if exe is None:
        raise ConvertError(f"{cmd[0]} is not installed")
    result = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True)
    if result.returncode != 0:
        raise ConvertError(result.stderr.strip() or f"{cmd[0]} failed")


def run_ffmpeg(args):
    # -n so ffmpeg itself refuses to overwrite if we ever get a race
    _run(["ffmpeg", "-nostdin", "-n", "-loglevel", "error", *args])


def _ffmpeg(src, out, _ext):
    run_ffmpeg(["-i", str(src), str(out)])


def load_image(src):
    from PIL import Image, ImageOps

    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass

    if ext_of(src) == "svg":
        import io

        import cairosvg
        return Image.open(io.BytesIO(cairosvg.svg2png(url=str(src))))
    # phones store the rotation as a tag, and other formats don't carry it, so apply it now
    return ImageOps.exif_transpose(Image.open(src))


def save_image(img, out, ext, **options):
    from PIL import Image

    fmt = {"jpg": "JPEG", "tiff": "TIFF", "pdf": "PDF", "heic": "HEIF"}.get(ext, ext.upper())
    if img.mode == "CMYK" and fmt != "JPEG":
        img = img.convert("RGB")
    if fmt in ("JPEG", "BMP", "PDF") and img.mode in ("RGBA", "LA", "P"):
        # these can't keep transparency, so flatten onto white instead of black
        img = img.convert("RGBA")
        flat = Image.new("RGB", img.size, "white")
        flat.paste(img, mask=img.getchannel("A"))
        img = flat
    img.save(out, fmt, **options)


def _image(src, out, ext):
    save_image(load_image(src), out, ext)


def _scratch(out):
    return tempfile.TemporaryDirectory(dir=Path(out).parent, prefix=".citrusina-")


def _office_scratch(out, exe):
    # a snap only sees its own corner of the disk, never the real /tmp
    if exe.startswith("/snap/"):
        home = Path.home() / "snap" / Path(exe).name / "common"
        home.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=home, prefix="citrusina-")
    return _scratch(out)


def _soffice(src, out, ext):
    exe = which("soffice")
    if exe is None:
        raise ConvertError("LibreOffice is not installed")
    with _office_scratch(out, exe) as tmp:
        # LibreOffice picks how to open a file by its name, so hand it a copy with a real one
        copy = Path(tmp) / f"{formats.base_name(src) or 'file'}.{ext_of(src)}"
        shutil.copyfile(src, copy)
        # its own profile dir, or it refuses to run while LibreOffice is open
        _run(["soffice", f"-env:UserInstallation=file://{tmp}/profile", "--headless",
              "--convert-to", ext, "--outdir", tmp, str(copy)])
        made = Path(tmp) / f"{copy.stem}.{ext}"
        if not made.exists():
            raise ConvertError("LibreOffice produced nothing")
        shutil.move(made, out)


def _pandoc(src, out, reader, writer):
    _run(["pandoc", "-f", reader, "-t", writer, str(src), "-o", str(out)])


# plain text has no pandoc reader of its own, markdown with hard breaks keeps the lines as typed
READERS = {"txt": "markdown+hard_line_breaks", "md": "markdown", "html": "html", "docx": "docx"}


def _document(src, out, ext):
    s = ext_of(src)
    if (s, ext) not in DOC_ROUTES:
        raise ConvertError(f"can't turn {s} into {ext}")
    if s == "pdf":
        _run(["pdftotext", "-layout", str(src), str(out)])
    elif ext == "pdf" and s == "md":
        with _scratch(out) as tmp:
            page = Path(tmp) / f"{Path(src).stem}.html"
            _pandoc(src, page, "markdown", "html5")
            _soffice(page, out, ext)
    elif ext == "pdf":
        _soffice(src, out, ext)
    else:
        # without -t plain, a .txt result comes out as markdown (backslashes and all)
        writer = {"txt": "plain", "md": "gfm"}.get(ext, ext)
        _pandoc(src, out, READERS[s], writer)


def _text(src, out, ext):
    s = ext_of(src)
    if ext in RICH:
        _document(src, out, ext)
        return
    # pandoc does the real thing for markup when it's there, text.py falls back to keeping the words
    if which("pandoc") and ((s == "md" and ext == "html") or (s == "html" and ext in ("md", "txt"))):
        _pandoc(src, out, READERS[s], {"html": "html5", "md": "gfm", "txt": "plain"}[ext])
        return
    result = text.transform(s, ext, text.read(src), formats.base_name(src))
    # newline="" keeps the line endings the file came with
    with open(out, "x", encoding="utf-8", newline="") as f:
        f.write(result)


def _unpack(src, dest):
    s = ext_of(src)
    if s == "zip":
        with zipfile.ZipFile(src) as z:
            z.extractall(dest)
    elif s in ("tar", "tar.gz"):
        with tarfile.open(src) as t:
            # the data filter refuses paths that escape dest, links to elsewhere and so on
            t.extractall(dest, filter="data")
    elif s == "rar":
        _run(["7z", "x", "-y", f"-o{dest}", str(src)])


def _pack(folder, out, ext):
    entries = sorted(Path(folder).iterdir())
    if ext == "zip":
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for entry in entries:
                for p in [entry, *entry.rglob("*")]:
                    z.write(p, p.relative_to(folder))
    else:
        with tarfile.open(out, "w:gz" if ext == "tar.gz" else "w") as t:
            for entry in entries:
                t.add(entry, entry.name)


def _archive(src, out, ext):
    # unpack and repack: slower than streaming but the same code handles every pair
    with tempfile.TemporaryDirectory() as tmp:
        _unpack(src, tmp)
        _pack(tmp, out, ext)


BACKENDS = {
    "image": _image,
    "video": _ffmpeg,
    "audio": _ffmpeg,
    "subtitle": _ffmpeg,
    "text": _text,
    "document": _document,
    "archive": _archive,
}


def convert(src, ext):
    ext = normalize(ext)
    kind = formats.kind_of(src)
    if kind is None or ext not in formats.KINDS[kind]["out"]:
        raise ConvertError(f"can't turn {Path(src).name} into {ext}")
    out = output_path(src, ext)
    try:
        BACKENDS[kind](src, out, ext)
    except ConvertError:
        out.unlink(missing_ok=True)
        raise
    except Exception as e:
        out.unlink(missing_ok=True)
        raise ConvertError(str(e)) from e
    return out
