# Copy into ~/.local/share/nautilus-python/extensions/ (needs python3-nautilus),
# or run packaging/linux/install.sh which does it for you.
import subprocess

from gi.repository import GObject, Nautilus


class CitrusinaMenu(GObject.GObject, Nautilus.MenuProvider):
    def get_file_items(self, files):
        if not files or any(f.get_uri_scheme() != "file" or f.is_directory() for f in files):
            return []
        paths = [f.get_location().get_path() for f in files]
        item = Nautilus.MenuItem(name="Citrusina::Convert", label="Convert with citrusina")
        item.connect("activate", lambda _item: subprocess.Popen(["citrusina", *paths]))
        return [item]
