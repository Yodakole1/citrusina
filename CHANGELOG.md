# Changelog

## 0.1.0 - 2026-10-23

First release.

- Drag a file onto the glass tab on the screen edge (or Shift+drag it on X11) and a wheel
  opens under the pointer. Drop it on a format to convert. Tap Shift, Tab or the middle to
  switch to tools. Type to search, Esc to close.
- Converts images, video, audio, text, documents, subtitles and archives. Results go next to
  the original and never overwrite anything. A toast shows the result in Files.
- Text converts to md, html, json, csv, yaml, xml, toml, ini and source formats. Data formats
  always come out valid, and files with no extension are recognised by their content.
- Tools: compress, crop, edit, annotate, add background, redact and strip metadata for images.
  Compress, trim, speed and snapshot for video. Normalize, trim and channels for audio. Tools
  with settings open an editor with a live preview.
- Settings (`citrusina --settings`): per kind of file, choose which formats and tools the wheel
  shows and in what order. Also the drop tab, start at login and the drag key.
- Several files at once, a single running instance, and a log at
  `~/.local/state/citrusina/log.txt` (`-v` to watch it).
- `packaging/linux/install.sh` adds the app entry, Open With and the Files right-click menu.
