"""Text to text. No Qt here.

Code formats (py, js, sh...) and plain ones (txt, md, log) just take the text as it is: a note
saved as a script is still the same words. Data formats have to come out valid, or the next
program refuses the file, so for those the text is read as data where it is data (json, csv,
toml, ini) and otherwise wrapped as a single string in the target's own syntax.
"""
import configparser
import csv
import html
import html.parser
import io
import json
import re
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

NOTHING = object()
# characters XML 1.0 can't hold at all, and a few others that make YAML blocks fragile
XML_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
YAML_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\r\ufeff]")
BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


def read(src):
    # most files are utf-8, but old Windows notes aren't, and latin-1 never fails
    data = Path(src).read_bytes()
    encodings = ["utf-8-sig", "cp1252", "latin-1"]
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        encodings.insert(0, "utf-16")
    for enc in encodings:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass


class _TextOnly(html.parser.HTMLParser):
    SKIP = ("script", "style", "head")
    BREAKS = ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6")

    def __init__(self):
        super().__init__()
        self.parts, self.skipping = [], 0

    def handle_starttag(self, tag, _attrs):
        self.skipping += tag in self.SKIP
        if tag in self.BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        self.skipping -= tag in self.SKIP and self.skipping > 0

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def strip_tags(page):
    parser = _TextOnly()
    parser.feed(page)
    return "".join(parser.parts).strip() + "\n"


# ---- reading text as data ----

def _ini(text):
    cp = configparser.RawConfigParser()
    cp.optionxform = str
    cp.read_string(text)
    return cp


def _csv_rows(text):
    """A table if the text clearly is one: a delimiter that gives every line the same width."""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    try:
        dialect = csv.Sniffer().sniff("\n".join(lines[:50]), delimiters=",;\t|")
    except csv.Error:
        return None
    rows = list(csv.reader(io.StringIO(text), dialect))
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if len({len(r) for r in rows}) != 1 or len(rows[0]) < 2:
        return None
    return rows


def parse(src_ext, text):
    """The data in the text, or NOTHING when it's just words."""
    try:
        if src_ext == "csv":
            rows = _csv_rows(text)
            if rows:
                head, *body = rows
                return [dict(zip(head, r)) for r in body]
        if src_ext == "toml":
            return tomllib.loads(text)
        if src_ext == "ini":
            cp = _ini(text)
            data = {s: dict(cp[s]) for s in cp.sections()}
            return data or NOTHING
        # json first for everything else: a .txt holding json is still json
        return json.loads(text)
    except (ValueError, configparser.Error):
        return NOTHING


def valid(ext, text):
    """Whether the text already is that format, in which case it's kept exactly as it was."""
    try:
        if ext == "json":
            json.loads(text)
        elif ext == "toml":
            tomllib.loads(text)
        elif ext == "ini":
            _ini(text)
        elif ext == "xml":
            ET.fromstring(text)
        elif ext == "csv":
            return text.strip() == "" or _csv_rows(text) is not None
        elif ext == "yaml":
            # no yaml parser in the standard library, but json and nothing at all are both yaml
            return text.strip() == "" or valid("json", text)
        else:
            return True
    except (ValueError, configparser.Error, ET.ParseError):
        return False
    return True


# ---- writing ----

def _cell(v):
    if v is None:
        return ""
    if isinstance(v, (dict, list, bool)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def to_json(data, text):
    value = text if data is NOTHING else data
    return json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n"


def to_csv(data, text):
    buf = io.StringIO()
    if data is NOTHING:
        rows = [[line] for line in text.splitlines()]
    elif isinstance(data, dict) and data and all(isinstance(v, dict) for v in data.values()):
        # sections, from ini or toml: one row per setting
        rows = [["section", "key", "value"]] + [[s, k, _cell(v)] for s, d in data.items()
                                                for k, v in d.items()]
    else:
        records = [data] if isinstance(data, dict) else data if isinstance(data, list) else [data]
        if records and all(isinstance(r, dict) for r in records):
            fields = list(dict.fromkeys(k for r in records for k in r))
            w = csv.DictWriter(buf, fields)
            w.writeheader()
            w.writerows({k: _cell(v) for k, v in r.items()} for r in records)
            return buf.getvalue()
        rows = [[_cell(c) for c in r] if isinstance(r, list) else [_cell(r)] for r in records]
    csv.writer(buf).writerows(rows)
    return buf.getvalue()


def _tag(key):
    tag = re.sub(r"[^\w.-]", "_", str(key)) or "item"
    return tag if re.match(r"[A-Za-z_]", tag) else f"_{tag}"


def _build(el, value):
    if isinstance(value, dict):
        for k, v in value.items():
            _build(ET.SubElement(el, _tag(k)), v)
    elif isinstance(value, list):
        for v in value:
            _build(ET.SubElement(el, "item"), v)
    elif value is not None:
        el.text = XML_BAD.sub("", _cell(value))


def to_xml(data, text):
    if data is NOTHING:
        root = ET.Element("text")
        root.text = XML_BAD.sub("", text)
    else:
        root = ET.Element("data")
        _build(root, data)
        ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def to_yaml(data, text):
    if data is not NOTHING:
        # json is valid yaml, and it can't get indentation wrong
        return json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n"
    if text == "" or YAML_BAD.search(text):
        return json.dumps(text, ensure_ascii=False) + "\n"
    # a literal block keeps the text readable. The 2 says how far it's indented, so a first
    # line that starts with spaces isn't misread, and the chomping sign keeps the line ends exact
    chomp = "+" if text.endswith("\n\n") else "" if text.endswith("\n") else "-"
    body = text[:-1] if text.endswith("\n") else text
    return f"|2{chomp}\n" + "".join(f"  {line}\n" if line else "\n" for line in body.split("\n"))


def _toml_key(k):
    k = str(k)
    return k if BARE_KEY.fullmatch(k) else json.dumps(k, ensure_ascii=False)


def _toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)      # inf and nan come out spelled the way toml wants
    if isinstance(v, dict):
        # toml has no null, so a missing value is simply left out
        return "{ " + ", ".join(f"{_toml_key(k)} = {_toml_value(x)}"
                                for k, x in v.items() if x is not None) + " }"
    if isinstance(v, list):
        return "[" + ", ".join('""' if x is None else _toml_value(x) for x in v) + "]"
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return json.dumps(str(v), ensure_ascii=False)


def _toml_text(text):
    # a multi-line string, with every quote and backslash escaped so nothing can end it early
    body = text.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r")
    body = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", lambda m: f"\\u{ord(m.group()):04x}", body)
    return f'"""\n{body}"""'


def to_toml(data, text):
    if data is NOTHING:
        return f"text = {_toml_text(text)}\n"
    if not isinstance(data, dict):
        data = {"rows" if isinstance(data, list) else "value": data}
    # plain keys have to come before any [table]
    lines = [f"{_toml_key(k)} = {_toml_value(v)}" for k, v in data.items()
             if v is not None and not isinstance(v, dict)]
    for k, v in data.items():
        if isinstance(v, dict):
            lines += ["", f"[{_toml_key(k)}]"]
            lines += [f"{_toml_key(x)} = {_toml_value(y)}" for x, y in v.items() if y is not None]
    return "\n".join(lines).lstrip("\n") + "\n"


def to_ini(data, text):
    cp = configparser.RawConfigParser()
    cp.optionxform = str
    if data is NOTHING:
        # leading spaces don't survive in ini values, everything else does
        cp["text"] = {"content": text.rstrip("\n")}
    else:
        if not isinstance(data, dict):
            data = {"value": data}
        flat = {k: v for k, v in data.items() if not isinstance(v, dict)}
        if flat:
            cp["data"] = {str(k): _cell(v) for k, v in flat.items()}
        for k, v in data.items():
            if isinstance(v, dict):
                cp[str(k)] = {str(x): _cell(y) for x, y in v.items()}
    buf = io.StringIO()
    cp.write(buf)
    return buf.getvalue()


def to_html(title, text):
    return (f'<!doctype html>\n<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"</head>\n<body>\n<pre>{html.escape(text)}</pre>\n</body></html>\n")


WRITERS = {"json": to_json, "csv": to_csv, "xml": to_xml, "yaml": to_yaml, "toml": to_toml,
           "ini": to_ini}


def transform(src_ext, ext, text, title):
    if src_ext == "html" and ext in ("txt", "md", "log"):
        return strip_tags(text)
    if ext == "html":
        return to_html(title, text)
    if ext not in WRITERS or valid(ext, text):
        return text
    return WRITERS[ext](parse(src_ext, text), text)
