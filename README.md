# citrusina

Convert and edit files from a glass wheel that opens right under your pointer. Drag a file onto
the little glass tab on the edge of the screen, keep dragging onto a format and let go.
A Linux take on Tangerine and DragShift, aimed at GNOME first.

## How you use it

- **Drop tab.** Drag a file onto the glass tab on the screen edge. The wheel unfolds under the pointer. Drop
  on a petal to convert, or drop on the middle to keep the wheel open and pick with a click.
- **Shift+drag** (X11 only). Hold Shift while dragging a file anywhere and the wheel opens under
  it. Wayland doesn't let apps watch input outside their own windows, so there the tab
  does this job.
- **Files menu.** Right-click one or more files → *Convert with citrusina*, or *Open With → citrusina*.

On the wheel:

- Click a petal to convert, click the middle (or tap Shift, or Tab) to flip between
  **convert** and **tools**.
- Start typing to search formats, arrows to move, Enter to pick, Esc to close.
- Several files at once convert to the formats they all share.

Results land next to the original and never overwrite anything. A toast says when they're done.
Click it to see the file in Files.

## Tools

Tools that need settings open an editor with a live preview. Hold the mouse on the preview to
compare it with the original.

- Images: Compress, Metadata (strip), Edit (rotate, flip, brightness, contrast, saturation),
  Annotate, Add BG, Crop, Redact
- Video: Compress, Trim, Speed, Snapshot
- Audio: Normalize, Trim, Channels

## What it converts

- Images: JPEG, PNG, HEIC, WebP, TIFF, BMP, GIF, PDF out; SVG in
- Video: MP4, MOV, MKV, AVI, WMV, WebM
- Audio: MP3, M4A, WAV, FLAC, OGG, Opus, AIFF
- Text: TXT, Markdown, HTML, JSON, CSV, YAML, XML, TOML, INI and source files (py, js, ts, sh,
  css, c, cpp, java, rs, go, log) into each other. Code and plain formats keep the text exactly.
  Data formats always come out valid: real data (json, csv, toml, ini) is converted, plain words
  are stored as text in that format. With pandoc, Markdown and HTML convert for real. Files with
  no extension are recognised by their content
- Documents: PDF to TXT/MD, DOCX to TXT/MD/PDF, TXT/MD/HTML to DOCX (needs pandoc) and to PDF
  (needs LibreOffice)
- Subtitles: SRT, VTT
- Archives: ZIP, TAR, TAR.GZ out; RAR in

## Installing from source

You need Python 3.10+ and a few command line tools. On Debian/Ubuntu:

```bash
sudo apt install ffmpeg pandoc poppler-utils p7zip-full libxcb-cursor0 python3-venv
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/citrusina            # runs in the background with the drop tab
```

For the app grid, *Open With* and the Files right-click entry (that last one needs
`python3-nautilus`):

```bash
sudo apt install python3-nautilus
packaging/linux/install.sh
```

Right-click the tab and pick *Settings…*, or run `citrusina --settings`:

- **Formats:** for each kind of file (images, text, documents...) tick which formats the
  wheel offers and drag them into order, so PDF can come before JSON or the other way round.
  The first 10 fit on the wheel, type on it to find the rest.
- **Tools:** the same for the tools ring.
- **General:** the drop tab, start at login, and on X11 the drag trigger key.

Changes save straight away to `~/.config/citrusina/settings.json`. The log is in
`~/.local/state/citrusina/log.txt` (*Open log* in the tab menu), add `-v` to any command to
watch it in the terminal.

On a GNOME Wayland session citrusina runs through XWayland so the wheel can open at the pointer.

## Command line

The commands below need no GUI, so scripts or other front ends can use them.

```
citrusina                           run in the background, with the drop tab
citrusina FILE...                   open the wheel for these files
citrusina --settings                choose which formats and tools show, and their order
citrusina --targets FILE            list formats and tools as json
citrusina --convert FILE EXT        convert and print the new file
citrusina --tool FILE KEY [k=v...]  run a tool and print the new file
```

## Status

Conversion and tools are covered by tests. The wheel, drop tab and editor haven't had much
real-desktop testing yet, Shift+drag on X11 and desktops other than GNOME least of all. See
[CONTRIBUTING.md](CONTRIBUTING.md) if you want to help.
