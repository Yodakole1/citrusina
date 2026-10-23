#!/bin/sh
# Adds citrusina to the app grid, the Open With list and the Files right-click menu, for this user.
set -e
here=$(dirname "$0")
data=${XDG_DATA_HOME:-$HOME/.local/share}
mkdir -p "$data/applications" "$data/icons/hicolor/scalable/apps" "$data/nautilus-python/extensions"
cp "$here/citrusina.desktop" "$data/applications/"
cp "$here/../../src/citrusina/assets/citrusina.svg" "$data/icons/hicolor/scalable/apps/"
cp "$here/../../nautilus/citrusina_nautilus.py" "$data/nautilus-python/extensions/"
update-desktop-database "$data/applications" 2>/dev/null || true
echo "Done. Restart Files with: nautilus -q"
