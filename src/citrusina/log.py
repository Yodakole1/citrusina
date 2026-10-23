"""The log at ~/.local/state/citrusina/log.txt, and on stderr too with -v.

Kept small and rotated, it's for "what happened when I dropped that file", not a diary.
"""
import logging
import logging.handlers
import os
import sys
from pathlib import Path

log = logging.getLogger("citrusina")


def path():
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(base) / "citrusina" / "log.txt"


def setup(verbose=False):
    if log.handlers:
        return
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    try:
        path().parent.mkdir(parents=True, exist_ok=True)
        f = logging.handlers.RotatingFileHandler(path(), maxBytes=1_000_000, backupCount=2,
                                                 encoding="utf-8")
        f.setFormatter(fmt)
        f.setLevel(logging.DEBUG)
        log.addHandler(f)
    except OSError:
        pass
    err = logging.StreamHandler()
    err.setFormatter(fmt)
    err.setLevel(logging.DEBUG if verbose else logging.WARNING)
    log.addHandler(err)

    # crashes in Qt callbacks would otherwise only reach a terminal nobody is looking at
    def hook(kind, value, tb):
        log.critical("crashed", exc_info=(kind, value, tb))
    sys.excepthook = hook
