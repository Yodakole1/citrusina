# Changelog

## Unreleased

- Rebuilt on Qt (PySide6) with a liquid-glass wheel, DragShift style: drag a file onto the drop
  tab or Shift+drag it (X11), then drop it on a petal. Shift, Tab or the middle flips between
  convert and tools.
- Tool settings open in a glass editor with a live preview, replacing the old GTK dialog.
- Runs in the background (`citrusina`) with the tab, a tray icon where there is one, start at
  login, and a toast that shows the result in Files. A second launch hands its files over.
- Several files at once from the Files menu.
- Files whose name says nothing (`tmp`, `README`, `notes.conf`) are judged by their content.
- Settings window (`citrusina --settings`): per kind of file, choose which formats and tools
  the wheel shows and in what order.
- Text to json, csv, xml, yaml, toml and ini always gives a valid file.
- A log at `~/.local/state/citrusina/log.txt`, `-v` to see it live, *Open log* in the tab menu.
- Text files convert to the usual text formats (md, html, json, csv, py, sh...) with no extra
  tools. pandoc and LibreOffice are found inside a venv too, and as the `libreoffice` snap.
- `packaging/linux/install.sh` adds the app entry, icon, Open With and the Files menu.
- First skeleton: Tangerine-style format list, conversion backends, GTK4 wheel, Nautilus menu entry.
