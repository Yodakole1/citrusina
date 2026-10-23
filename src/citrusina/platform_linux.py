"""The bits that depend on the Linux desktop. No Qt here."""
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def session():
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return "wayland"
    return "x11" if os.environ.get("DISPLAY") else "unknown"


def global_input():
    """Whether we can watch the mouse and keys outside our own windows, which Shift+drag needs.
    Under XWayland we'd only see what happens over other X windows, so that doesn't count."""
    return session() == "x11"


# what Qt's xcb plugin links against that a Wayland-only system often lacks
XCB_LIBS = ("libxcb-cursor.so.0", "libxkbcommon-x11.so.0", "libxcb-icccm.so.4",
            "libxcb-keysyms.so.1", "libxcb-xkb.so.1")


def _xcb_libs_load():
    """Load the xcb plugin's libraries up front, from the system or next to our Python.

    Once a library is loaded its name is taken, so the plugin finds it later even though
    the pip build of Qt never looks in our prefix.
    """
    import ctypes
    for name in XCB_LIBS:
        for candidate in (name, os.path.join(sys.prefix, "lib", name)):
            try:
                ctypes.CDLL(candidate, mode=ctypes.RTLD_GLOBAL)
                break
            except OSError:
                continue
        else:
            return False
    return True


def use_xwayland():
    # Wayland won't let a window choose where it opens, and the wheel has to open at the pointer.
    # Plain wayland stays as the fallback in case XWayland refuses us anyway.
    if session() == "wayland" and os.environ.get("DISPLAY") and "QT_QPA_PLATFORM" not in os.environ:
        if _xcb_libs_load():
            os.environ["QT_QPA_PLATFORM"] = "xcb;wayland"
        else:
            print("citrusina: install libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 "
                  "libxcb-keysyms1 so the wheel can open at the pointer", file=sys.stderr)


def dark_mode():
    try:
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                             capture_output=True, text=True, timeout=1).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "dark" in out


def reveal(path):
    """Show a file selected in the file manager."""
    uri = Path(path).absolute().as_uri()
    try:
        done = subprocess.run(
            ["gdbus", "call", "--session", "--dest", "org.freedesktop.FileManager1",
             "--object-path", "/org/freedesktop/FileManager1",
             "--method", "org.freedesktop.FileManager1.ShowItems", f"['{uri}']", ""],
            capture_output=True, timeout=3)
        if done.returncode == 0:
            return
    except (OSError, subprocess.TimeoutExpired):
        pass
    if shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", str(Path(path).parent)])


def config_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base)


def autostart_file():
    return config_dir() / "autostart" / "citrusina.desktop"


def set_autostart(enabled):
    f = autostart_file()
    if not enabled:
        f.unlink(missing_ok=True)
        return
    f.parent.mkdir(parents=True, exist_ok=True)
    # the interpreter we're running in, so it works the same from a venv
    exec_line = f"{shlex.quote(sys.executable)} -m citrusina --background"
    f.write_text("[Desktop Entry]\nType=Application\nName=citrusina\n"
                 f"Exec={exec_line}\nIcon=citrusina\n"
                 "Comment=Convert files from a circle by the pointer\n"
                 "X-GNOME-Autostart-enabled=true\n")
