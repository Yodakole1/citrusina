"""The tools wheel: things you do to a file without changing its format.

Image tools are plain functions on a PIL image so the editor can run them on a small
thumbnail for a live preview. Everything is sized in percent for the same reason, a
crop that looks right on the thumbnail has to look the same on the full photo.
Video and audio tools build an ffmpeg command instead.
"""
from dataclasses import dataclass, field

from citrusina import convert, formats
from citrusina.convert import ConvertError


@dataclass
class Param:
    key: str
    label: str
    kind: str                       # "int", "choice", "text"
    default: object = None
    lo: int = 0
    hi: int = 100
    choices: tuple = ()


@dataclass
class Tool:
    key: str
    label: str
    kind: str
    suffix: str
    params: list = field(default_factory=list)
    apply: object = None            # image tools: (img, **values) -> img
    build: object = None            # media tools: (src, out, **values) -> ffmpeg args
    out_ext: object = None          # ext for the result, defaults to the source's

    def defaults(self):
        return {p.key: p.default for p in self.params}


# ---- images ----

def crop(img, aspect="free", left=0, top=0, right=0, bottom=0):
    w, h = img.size
    box = [round(w * left / 100), round(h * top / 100),
           w - round(w * right / 100), h - round(h * bottom / 100)]
    if box[2] - box[0] < 1 or box[3] - box[1] < 1:
        return img
    img = img.crop(box)
    if aspect != "free":
        rw, rh = (int(n) for n in aspect.split(":"))
        w, h = img.size
        if w * rh > h * rw:
            nw = max(1, h * rw // rh)
            x = (w - nw) // 2
            img = img.crop((x, 0, x + nw, h))
        else:
            nh = max(1, w * rh // rw)
            y = (h - nh) // 2
            img = img.crop((0, y, w, y + nh))
    return img


def redact(img, left=30, top=40, width=40, height=20, style="black"):
    from PIL import Image, ImageFilter

    w, h = img.size
    box = (round(w * left / 100), round(h * top / 100),
           min(w, round(w * (left + width) / 100)), min(h, round(h * (top + height) / 100)))
    if box[2] <= box[0] or box[3] <= box[1]:
        return img
    img = img.convert("RGBA")
    part = img.crop(box)
    if style == "black":
        part = Image.new("RGBA", part.size, (0, 0, 0, 255))
    elif style == "blur":
        part = part.filter(ImageFilter.GaussianBlur(max(part.size) / 6))
    else:
        small = (max(1, part.width // 12), max(1, part.height // 12))
        part = part.resize(small, Image.Resampling.BILINEAR).resize(part.size, Image.Resampling.NEAREST)
    img.paste(part, box[:2])
    return img


def adjust(img, rotate="0", flip="none", brightness=0, contrast=0, saturation=0):
    from PIL import Image, ImageEnhance

    if rotate != "0":
        img = img.rotate(-int(rotate), expand=True)
    if flip == "horizontal":
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    elif flip == "vertical":
        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    for enhancer, amount in ((ImageEnhance.Brightness, brightness),
                             (ImageEnhance.Contrast, contrast),
                             (ImageEnhance.Color, saturation)):
        if amount:
            img = enhancer(img).enhance(1 + amount / 100)
    return img


TEXT_COLORS = {"white": (255, 255, 255), "black": (0, 0, 0),
               "red": (235, 64, 52), "yellow": (250, 204, 21)}


def annotate(img, text="Hello", position="bottom", size=8, color="white"):
    from PIL import ImageDraw, ImageFont

    if not text:
        return img
    img = img.convert("RGBA")
    px = max(8, round(img.height * size / 100))
    try:
        font = ImageFont.load_default(size=px)
    except TypeError:
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(img)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    x = (img.width - (right - left)) / 2 - left
    margin = img.height * 0.04
    y = {"top": margin, "center": (img.height - (bottom - top)) / 2,
         "bottom": img.height - (bottom - top) - margin}[position] - top
    # a dark edge keeps light text readable on light photos
    edge = "white" if color == "black" else "black"
    draw.text((x, y), text, font=font, fill=TEXT_COLORS[color],
              stroke_width=max(1, px // 14), stroke_fill=edge)
    return img


BACKGROUNDS = {
    "sunset": ((255, 150, 60), (200, 60, 200)),
    "ocean": ((60, 190, 230), (50, 70, 200)),
    "mint": ((150, 235, 190), (40, 150, 130)),
    "lavender": ((235, 200, 250), (130, 110, 230)),
    "white": ((255, 255, 255), (235, 235, 240)),
    "black": ((50, 50, 55), (10, 10, 12)),
}


def add_background(img, background="sunset", padding=15, corners=6, shadow=12, ratio="auto"):
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    img = img.convert("RGBA")
    w, h = img.size
    pad = round(max(w, h) * padding / 100)
    cw, ch = w + 2 * pad, h + 2 * pad
    if ratio != "auto":
        rw, rh = (int(n) for n in ratio.split(":"))
        if cw * rh < ch * rw:
            cw = ch * rw // rh
        else:
            ch = cw * rh // rw

    c1, c2 = BACKGROUNDS[background]
    base = Image.linear_gradient("L")
    vertical = base.resize((cw, ch))
    horizontal = base.transpose(Image.Transpose.ROTATE_90).resize((cw, ch))
    mask = ImageChops.add(vertical, horizontal, scale=2)
    canvas = Image.composite(Image.new("RGB", (cw, ch), c2), Image.new("RGB", (cw, ch), c1), mask)
    canvas = canvas.convert("RGBA")

    x, y = (cw - w) // 2, (ch - h) // 2
    radius = round(min(w, h) * corners / 100)
    round_mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(round_mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)

    if shadow:
        blur = max(1, round(min(w, h) * shadow / 400))
        layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        dark = Image.new("RGBA", (w, h), (0, 0, 0, 120))
        layer.paste(dark, (x, y + blur), round_mask)
        canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))

    canvas.paste(img, (x, y), ImageChops.multiply(round_mask, img.getchannel("A")))
    return canvas


def strip_metadata(img):
    # nothing to do: loading already applied the rotation, and saving writes no exif
    return img.copy()


# compress needs the output format to choose its options, so it saves on its own
def compress_options(ext, quality):
    if ext in ("jpg", "webp", "heic"):
        return {"quality": quality, **({"optimize": True} if ext == "jpg" else {})}
    if ext == "png":
        return {"optimize": True}
    if ext == "tiff":
        return {"compression": "tiff_adobe_deflate"}
    return {}


def compress_image(img, ext, quality):
    from PIL import Image

    if ext == "png" and quality < 95:
        # fewer colors is where most of a png's size goes
        img = img.convert("RGBA").quantize(max(16, round(256 * quality / 100)),
                                           method=Image.Quantize.FASTOCTREE)
    return img


# ---- video and audio ----

def atempo(factor):
    """ffmpeg's atempo only takes 0.5 to 2, so bigger changes are chained."""
    parts = []
    while factor > 2:
        parts.append("atempo=2")
        factor /= 2
    while factor < 0.5:
        parts.append("atempo=0.5")
        factor /= 0.5
    parts.append(f"atempo={factor:g}")
    return ",".join(parts)


def _seconds(value):
    """Seconds as text, checked so nothing odd reaches ffmpeg's command line."""
    try:
        seconds = float(value or 0)
    except ValueError:
        raise ConvertError(f"{value!r} is not a number of seconds") from None
    if seconds < 0:
        raise ConvertError("time can't be negative")
    return f"{seconds:g}"


def _trim_args(start, end):
    args = ["-ss", _seconds(start)]
    if end:
        args += ["-to", _seconds(end)]
    return args


def video_compress(src, out, crf):
    return ["-i", str(src), "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
            "-c:a", "aac", "-b:a", "128k", str(out)]


def video_speed(src, out, speed):
    f = float(speed)
    return ["-i", str(src), "-vf", f"setpts=PTS/{f:g}", "-af", atempo(f), str(out)]


def trim(src, out, start, end):
    return ["-i", str(src), *_trim_args(start, end), str(out)]


def snapshot(src, out, time):
    return ["-ss", _seconds(time), "-i", str(src), "-frames:v", "1", str(out)]


def normalize(src, out):
    return ["-i", str(src), "-af", "loudnorm", str(out)]


def channels(src, out, mode):
    return ["-i", str(src), "-ac", "1" if mode == "mono" else "2", str(out)]


def _mp4_unless_mkv_or_mov(src):
    return formats.ext_of(src) if formats.ext_of(src) in ("mkv", "mov") else "mp4"


def pct(key, label, default, lo=0, hi=100):
    return Param(key, label, "int", default, lo, hi)


ASPECTS = ("free", "1:1", "16:9", "9:16", "4:3", "3:4")

IMAGE_TOOLS = [
    Tool("compress", "Compress", "image", "Compressed", [pct("quality", "Quality", 60, 10, 95)]),
    Tool("metadata", "Metadata", "image", "Clean", [], apply=strip_metadata),
    Tool("edit", "Edit", "image", "Edited", [
        Param("rotate", "Rotate", "choice", "0", choices=("0", "90", "180", "270")),
        Param("flip", "Flip", "choice", "none", choices=("none", "horizontal", "vertical")),
        pct("brightness", "Brightness", 0, -100, 100),
        pct("contrast", "Contrast", 0, -100, 100),
        pct("saturation", "Saturation", 0, -100, 100)], apply=adjust),
    Tool("annotate", "Annotate", "image", "Annotated", [
        Param("text", "Text", "text", "Hello"),
        Param("position", "Position", "choice", "bottom", choices=("top", "center", "bottom")),
        pct("size", "Size", 8, 2, 25),
        Param("color", "Color", "choice", "white", choices=tuple(TEXT_COLORS))], apply=annotate),
    Tool("add bg", "Add BG", "image", "With Background", [
        Param("background", "Background", "choice", "sunset", choices=tuple(BACKGROUNDS)),
        pct("padding", "Padding", 15, 0, 60),
        pct("corners", "Corners", 6, 0, 30),
        pct("shadow", "Shadow", 12, 0, 40),
        Param("ratio", "Ratio", "choice", "auto", choices=("auto", "1:1", "16:9", "4:5"))],
         apply=add_background, out_ext=lambda src: "png"),
    Tool("crop", "Crop", "image", "Cropped", [
        Param("aspect", "Aspect ratio", "choice", "free", choices=ASPECTS),
        pct("left", "Left", 0, 0, 45), pct("top", "Top", 0, 0, 45),
        pct("right", "Right", 0, 0, 45), pct("bottom", "Bottom", 0, 0, 45)], apply=crop),
    Tool("redact", "Redact", "image", "Redacted", [
        pct("left", "Left", 30, 0, 95), pct("top", "Top", 40, 0, 95),
        pct("width", "Width", 40, 1, 100), pct("height", "Height", 20, 1, 100),
        Param("style", "Style", "choice", "black", choices=("black", "pixelate", "blur"))],
         apply=redact),
]

VIDEO_TOOLS = [
    Tool("compress", "Compress", "video", "Compressed", [pct("crf", "Quality loss", 28, 18, 40)],
         build=video_compress, out_ext=_mp4_unless_mkv_or_mov),
    Tool("trim", "Trim", "video", "Trimmed", [
        Param("start", "Start (seconds)", "text", "0"), Param("end", "End (seconds)", "text", "")],
         build=trim),
    Tool("speed", "Speed", "video", "Speed", [
        Param("speed", "Speed", "choice", "2", choices=("0.25", "0.5", "1.5", "2", "4"))],
         build=video_speed),
    Tool("snapshot", "Snapshot", "video", "Snapshot", [Param("time", "At (seconds)", "text", "0")],
         build=snapshot, out_ext=lambda src: "png"),
]

AUDIO_TOOLS = [
    Tool("normalize", "Normalize", "audio", "Normalized", [], build=normalize),
    Tool("trim", "Trim", "audio", "Trimmed", [
        Param("start", "Start (seconds)", "text", "0"), Param("end", "End (seconds)", "text", "")],
         build=trim),
    Tool("channels", "Channels", "audio", "Channels", [
        Param("mode", "Channels", "choice", "mono", choices=("mono", "stereo"))], build=channels),
]

TOOLS = {"image": IMAGE_TOOLS, "video": VIDEO_TOOLS, "audio": AUDIO_TOOLS}


def tools_for(path):
    return TOOLS.get(formats.kind_of(path), [])


def run(tool, src, values=None):
    """Apply a tool to a file and return the new file, which sits beside the original."""
    values = {**tool.defaults(), **(values or {})}
    ext = tool.out_ext(src) if tool.out_ext else formats.ext_of(src)
    if tool.kind == "image" and formats.ext_of(src) == "svg":
        ext = "png"
    out = convert.output_path(src, ext, tool.suffix)
    try:
        if tool.kind == "image":
            _run_image(tool, src, out, ext, values)
        else:
            convert.run_ffmpeg(tool.build(src, out, **values))
    except ConvertError:
        out.unlink(missing_ok=True)
        raise
    except Exception as e:
        out.unlink(missing_ok=True)
        raise ConvertError(str(e)) from e
    return out


def _run_image(tool, src, out, ext, values):
    img = convert.load_image(src)
    options = {}
    if tool.key == "compress":
        options = compress_options(ext, values["quality"])
        img = compress_image(img, ext, values["quality"])
    else:
        img = tool.apply(img, **values)
    convert.save_image(img, out, ext, **options)


def preview(tool, img, values):
    """What the editor shows: the tool run on a thumbnail."""
    if tool.apply is None:
        return img
    return tool.apply(img, **{**tool.defaults(), **values})
