"""Preferences in ~/.config/citrusina/settings.json.

Besides a few switches, people choose what each ring shows and in what order, per kind of file:
which formats a document gets, whether PDF comes before JSON, which tools show up at all.
Only what they changed is stored, so formats added in a later version still turn up.
"""
import copy
import json

from citrusina import platform_linux

DEFAULTS = {
    "trigger": "shift",     # held while dragging a file, X11 only
    "bubble": True,         # the drop tab on the screen edge
    "bubble_pos": None,     # [x, y] once it's been moved
    # {"rings": {"convert": {"text": {"order": ["pdf", "md"], "hidden": ["log"]}}, "tools": {...}}}
    "rings": {"convert": {}, "tools": {}},
}
TRIGGERS = ("shift", "ctrl", "alt")


def path():
    return platform_linux.config_dir() / "citrusina" / "settings.json"


def _clean_rings(rings):
    clean = {"convert": {}, "tools": {}}
    if not isinstance(rings, dict):
        return clean
    for ring in clean:
        kinds = rings.get(ring)
        if not isinstance(kinds, dict):
            continue
        for kind, choice in kinds.items():
            if not isinstance(choice, dict):
                continue
            lists = {k: [x for x in choice.get(k, []) if isinstance(x, str)]
                     for k in ("order", "hidden") if isinstance(choice.get(k, []), list)}
            clean[ring][str(kind)] = {"order": lists.get("order", []), "hidden": lists.get("hidden", [])}
    return clean


def load():
    try:
        saved = json.loads(path().read_text())
    except (OSError, ValueError):
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    merged = {**copy.deepcopy(DEFAULTS), **{k: v for k, v in saved.items() if k in DEFAULTS}}
    if merged["trigger"] not in TRIGGERS:
        merged["trigger"] = DEFAULTS["trigger"]
    merged["rings"] = _clean_rings(merged["rings"])
    return merged


def save(values):
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".part")
    tmp.write_text(json.dumps(values, indent=2))
    tmp.replace(p)


def arrange(prefs, ring, kind, items):
    """items in the order the person chose, minus the ones they hid. Anything they've never
    seen (a format added since) goes at the end, so it isn't hidden just for being new."""
    choice = prefs.get("rings", {}).get(ring, {}).get(kind)
    if not choice:
        return list(items)
    hidden = set(choice["hidden"])
    first = [i for i in choice["order"] if i in items and i not in hidden]
    return first + [i for i in items if i not in first and i not in hidden]


def layout(prefs, ring, kind, items):
    """Everything, hidden ones included, in the chosen order, as (item, shown) pairs."""
    choice = prefs.get("rings", {}).get(ring, {}).get(kind) or {"order": [], "hidden": []}
    first = [i for i in choice["order"] if i in items]
    hidden = set(choice["hidden"])
    return [(i, i not in hidden) for i in first + [i for i in items if i not in first]]


def remember(prefs, ring, kind, order, hidden):
    prefs.setdefault("rings", {"convert": {}, "tools": {}}).setdefault(ring, {})[kind] = {
        "order": list(order), "hidden": list(hidden)}


def forget(prefs, ring, kind):
    prefs.get("rings", {}).get(ring, {}).pop(kind, None)
