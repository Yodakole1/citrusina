import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PIL import Image  # noqa: E402
from PySide6.QtCore import QPoint, QPointF  # noqa: E402

from citrusina import radial, wheel  # noqa: E402
from citrusina.app import rings_for  # noqa: E402

MID = (wheel.R_IN + wheel.R_OUT) / 2


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def png(tmp_path):
    p = tmp_path / "a.png"
    Image.new("RGB", (8, 8)).save(p)
    return str(p)


def test_petals_have_gaps_between_them(qapp):
    paths = radial.petal_paths(4)
    top, right = paths[0], paths[1]
    assert top.contains(QPointF(0, -MID))
    assert not top.contains(QPointF(*wheel.point(45, MID)))
    assert not right.contains(QPointF(*wheel.point(45, MID)))
    assert right.contains(QPointF(MID, 0))


def test_a_single_petal_is_a_ring_with_a_hole(qapp):
    (ring,) = radial.petal_paths(1)
    assert ring.contains(QPointF(0, MID))
    assert not ring.contains(QPointF(0, 0))


def test_rings_for_files(png, tmp_path):
    rings = rings_for([png])
    assert "jpg" in rings["convert"] and "png" not in rings["convert"]
    assert "crop" in rings["tools"]
    other = tmp_path / "b.webp"
    Image.new("RGB", (8, 8)).save(other)
    both = rings_for([png, str(other)])
    assert "png" not in both["convert"] and "webp" not in both["convert"]
    assert both["tools"] == []


def test_pick_tab_and_search(qapp, png):
    r = radial.Radial(rings_for)
    got = []
    r.picked.connect(lambda paths, ring, item: got.append((ring, item)))
    r.popup([png], QPoint(400, 400))
    r.resize(1000, 900)
    assert r.ring == "convert"
    r._set_query("we")
    assert r.shown == ["webp"]
    r._pick(0)
    assert got == [("convert", "webp")]
    r.switch_ring()
    assert r.ring == "tools" and r.query == ""
    r.hide()


def test_paints_without_errors(qapp, png):
    r = radial.Radial(rings_for)
    r.resize(800, 800)
    r.popup([png], QPoint(400, 400))
    r.resize(800, 800)
    r.hover = 0
    r.springs[0] = 1.0
    img = r.grab().toImage()
    assert img.width() > 0
    r.hide()


def test_settings_change_what_the_wheel_offers(png):
    from citrusina import settings
    prefs = settings.load()
    settings.remember(prefs, "convert", "image", ["pdf", "webp"], ["jpg"])
    rings = rings_for([png], prefs)
    assert rings["convert"][:2] == ["pdf", "webp"] and "jpg" not in rings["convert"]
