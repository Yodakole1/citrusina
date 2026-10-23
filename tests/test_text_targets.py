"""Every target a text file is offered must give a file the next program accepts."""
import configparser
import csv
import io
import json
import shutil
import tomllib
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser

import pytest

from citrusina import convert

yaml = pytest.importorskip("yaml")

PROSE = ('Hello "world" \\ back\\slash\n  indented line\n\ttab\nunicode: čćž 日本 🍊\n'
         '<tag> & ampersand, comma; semi\n"""triple""" \'\'\'single\'\'\'\n# not a comment\n\n')
SAMPLES = {
    "empty": "",
    "prose": PROSE,
    "one line": "no newline at the end",
    "json": '[{"name": "a", "n": 1, "tags": ["x"]}, {"name": "b", "ok": true, "none": null}]',
    "csv": "name,count\napple,3\npear,5\n",
    "ini": "[server]\nhost = example.org\nport = 8080\n",
    "toml": 'title = "demo"\n[owner]\nname = "kos"\n',
}
SLOW = ("pdf", "docx")


def check(ext, out, original):
    data = out.read_bytes()
    text = data.decode("utf-8") if ext not in SLOW else None
    if ext == "json":
        json.loads(text)
    elif ext == "csv":
        list(csv.reader(io.StringIO(text)))
    elif ext == "xml":
        ET.fromstring(text)
    elif ext == "yaml":
        yaml.safe_load(text)
    elif ext == "toml":
        tomllib.loads(text)
    elif ext == "ini":
        configparser.RawConfigParser().read_string(text)
    elif ext == "html":
        assert "<html" in text
        HTMLParser().feed(text)
    elif ext == "pdf":
        assert data.startswith(b"%PDF")
    elif ext == "docx":
        assert "word/document.xml" in zipfile.ZipFile(out).namelist()
    else:
        # code and plain formats keep the text byte for byte
        assert text == original, ext


@pytest.mark.parametrize("name", SAMPLES)
def test_every_target_is_valid(tmp_path, name):
    src = tmp_path / "tmp"          # no extension, like a file made on the desktop
    src.write_text(SAMPLES[name], encoding="utf-8")
    targets = convert.targets_for(src)
    assert {"md", "json", "csv", "xml", "yaml", "toml", "ini", "py"} <= set(targets)
    for ext in targets:
        if ext in SLOW and name != "prose":
            continue
        out = convert.convert(src, ext)
        check(ext, out, SAMPLES[name])


@pytest.mark.parametrize("name", ["prose", "one line", "empty"])
def test_plain_text_survives_inside_data_formats(tmp_path, name):
    words = SAMPLES[name]
    src = tmp_path / "note.txt"
    src.write_text(words, encoding="utf-8")
    out = {ext: convert.convert(src, ext).read_text(encoding="utf-8")
           for ext in ("json", "yaml", "toml", "xml")}
    assert json.loads(out["json"]) == words
    assert (ET.fromstring(out["xml"]).text or "") == words
    if words:
        assert yaml.safe_load(out["yaml"]) == words
        assert tomllib.loads(out["toml"])["text"] == words
    else:
        # empty is already a valid yaml and toml file, so it stays empty
        assert out["yaml"] == out["toml"] == ""


def test_data_moves_between_formats(tmp_path):
    src = tmp_path / "rows.txt"
    src.write_text(SAMPLES["json"])
    rows = json.loads(SAMPLES["json"])
    assert yaml.safe_load(convert.convert(src, "yaml").read_text()) == rows
    assert tomllib.loads(convert.convert(src, "toml").read_text())["rows"][0]["tags"] == ["x"]
    table = list(csv.DictReader(io.StringIO(convert.convert(src, "csv").read_text())))
    assert table[0]["name"] == "a" and table[1]["ok"] == "true"
    xml = ET.fromstring(convert.convert(src, "xml").read_text())
    assert [i.findtext("name") for i in xml] == ["a", "b"]

    ini = tmp_path / "app.ini"
    ini.write_text(SAMPLES["ini"])
    assert json.loads(convert.convert(ini, "json").read_text()) == {
        "server": {"host": "example.org", "port": "8080"}}
    assert tomllib.loads(convert.convert(ini, "toml").read_text())["server"]["port"] == "8080"

    table = tmp_path / "fruit.csv"
    table.write_text(SAMPLES["csv"])
    assert yaml.safe_load(convert.convert(table, "yaml").read_text())[1] == {"name": "pear", "count": "5"}


def test_text_that_already_is_the_format_is_kept_as_is(tmp_path):
    src = tmp_path / "config.txt"
    src.write_text(SAMPLES["toml"])
    assert convert.convert(src, "toml").read_text() == SAMPLES["toml"]


needs_office = pytest.mark.skipif(not (convert.which("soffice") and convert.which("pandoc")),
                                  reason="needs LibreOffice and pandoc")


@needs_office
def test_markdown_to_pdf(tmp_path):
    src = tmp_path / "readme.md"
    src.write_text("# Title\n\nSome *text*.\n")
    assert convert.convert(src, "pdf").read_bytes().startswith(b"%PDF")
    assert shutil.which("pdftotext") is None or "Title" in convert.convert(
        convert.convert(src, "docx"), "txt").read_text()
