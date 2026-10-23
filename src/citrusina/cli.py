"""Entry point. The --targets, --convert and --tool commands work without Qt, so other front
ends (a GNOME Shell extension, say) can call them and read the JSON."""
import json
import sys

from citrusina import convert, tools
from citrusina import log as logfile
from citrusina.log import log

USAGE = """usage: (add -v to see the log as it happens)
  citrusina                           run in the background, with the drop tab
  citrusina FILE...                   open the wheel for these files
  citrusina --settings                choose which formats and tools show, and their order
  citrusina --targets FILE            list formats and tools as json
  citrusina --convert FILE EXT        convert and print the new file
  citrusina --tool FILE KEY [k=v...]  run a tool and print the new file
"""


def describe(path):
    return {
        "convert": convert.targets_for(path),
        "tools": [{"key": t.key, "label": t.label,
                   "params": [{"key": p.key, "label": p.label, "kind": p.kind,
                               "default": p.default, "lo": p.lo, "hi": p.hi,
                               "choices": list(p.choices)} for p in t.params]}
                  for t in tools.tools_for(path)],
    }


def parse_values(tool, pairs):
    kinds = {p.key: p.kind for p in tool.params}
    values = {}
    for pair in pairs:
        key, _, raw = pair.partition("=")
        if key not in kinds:
            raise convert.ConvertError(f"{tool.label} has no setting called {key}")
        try:
            values[key] = int(raw) if kinds[key] == "int" else raw
        except ValueError:
            raise convert.ConvertError(f"{key} should be a number") from None
    return values


def gui(files, resident=False, action=None):
    # imported here, so the commands above need no Qt
    from citrusina import handoff
    log.info("launched with %s%s", files or "no files", f", {action}" if action else "")
    if handoff.try_handoff(files, action):
        return 0
    from citrusina import app
    return app.main(files, resident, settings_window=action == "settings")


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    verbose = any(a in ("-v", "--verbose") for a in args)
    args = [a for a in args if a not in ("-v", "--verbose")]
    logfile.setup(verbose)
    try:
        if len(args) == 2 and args[0] == "--targets":
            print(json.dumps(describe(args[1])))
        elif len(args) == 3 and args[0] == "--convert":
            print(convert.convert(args[1], args[2]))
        elif len(args) >= 3 and args[0] == "--tool":
            tool = next((t for t in tools.tools_for(args[1]) if t.key == args[2]), None)
            if tool is None:
                raise convert.ConvertError(f"no tool {args[2]} for {args[1]}")
            print(tools.run(tool, args[1], parse_values(tool, args[3:])))
        elif args == ["--settings"]:
            return gui([], action="settings")
        elif not args or args == ["--background"]:
            return gui([], resident=True)
        elif not any(a.startswith("-") for a in args):
            return gui(args)
        else:
            print(USAGE, file=sys.stderr)
            return 2
    except convert.ConvertError as e:
        print(f"citrusina: {e}", file=sys.stderr)
        return 1
    return 0
