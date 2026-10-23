# Contributing to citrusina

Thanks for helping. citrusina is early and small, so contributing is easy.

## The most useful thing you can do

**Try it on your setup and tell us what happened.** citrusina is built for GNOME on Linux first.
Anything on another desktop, another session type (Wayland vs X11) or another distro is
untested until someone reports back. A short report ("works on Fedora 41 with GNOME on Wayland" or
"the circle shows up but PDF to PNG fails") is a real contribution.

When you open an issue, please include:

- your desktop and session: `echo $XDG_CURRENT_DESKTOP $XDG_SESSION_TYPE`
- your distro and version
- the file type you tried to convert, and what you expected
- the log, `~/.local/state/citrusina/log.txt` (or run with `-v` to see it in the terminal)

## Setting up

```bash
git clone git@github.com:Yodakole1/citrusina.git
cd citrusina
git switch develop
```

```bash
python3 -m venv .venv   # see the README for the system packages
.venv/bin/pip install -e .
.venv/bin/pip install pytest
.venv/bin/python -m pytest
```

## Branches

- `main` is the stable branch. It always works and is what people clone and install from.
  Releases are tagged on it. Nobody commits to it directly.
- `develop` is where work comes together. Pull requests target `develop`.
- Work on a short-lived branch cut from `develop`, named for what it does (`fix-circle-position`,
  `add-heic-support`), and open the PR back into `develop`.
- When `develop` is tested and ready, the maintainer merges it into `main` and tags a release.
  A bad regression found on `main` can be fixed in a branch off `main` and merged into both.

```bash
git switch develop
git pull
git switch -c my-change
```

## Before you open a pull request

A pull request is a proposal, not a guarantee. It gets merged when it's correct, shown to work,
tested, reasonably small, and fits where the project is going. Something can be good and still not
be merged if it adds more upkeep than it's worth.

- **One topic per PR.** A bug fix, a new format and a refactor are three PRs.
- **Match the existing style.** Read the code around your change and write like it.
- **Don't break what already works.** New features must leave existing behavior, defaults and
  options alone unless the PR is specifically about changing them. If you change a default, say so loudly.
- **It has to run.** Build it, start it, and run the tests before you ask for review. If something
  fails to build or import, include the log.
- **Say how you tested.** See the next section. "Untested" is an acceptable answer as long as it's honest.
- **Be sparing with logging.** A log line should help someone diagnose a real problem. Don't narrate
  every step.
- **Comments explain why.** Write down design decisions and non-obvious details, not what the next
  line obviously does.

## Testing, and saying so

Every PR description must say what was tested and how. Tick the boxes in the PR template that are
true and leave the rest unticked with a short note. Nobody will be annoyed by "I couldn't test this on X11";
they will be annoyed by a claim that turns out not to be true.

There are two kinds of checking, and they cover different things:

1. **Automated tests.** Conversion is tested on small generated files with the real tools, and
   tests skip themselves when a tool isn't installed. New behavior should come with a test.
2. **Real desktop.** Anything touching the file manager integration, Shift+drag, the drop tab,
   the wheel or the converters themselves should be tried for real, and the PR should say on
   what: distro, desktop, session type, which file you converted and what you saw. If you couldn't
   try it on a real desktop, say that plainly. The maintainer may be able to.

## If AI helped you write it

That's allowed, with conditions. You own the change, not the tool.

- Write the PR description yourself, in your own words: what it does, why it's needed and what problem
  it solves. Don't paste a generated summary.
- Only submit code you understand well enough to explain and maintain. In review you'll be asked why it
  works this way, and "the AI wrote it" won't be accepted as an answer.
- Large generated changes that the author can't walk through will be turned down, even if they work.
- Skim the generated comments. Delete the ones that just restate the code.

## Making a change

- Keep it simple. Each file is meant to be readable in one sitting. The logic (`formats.py`,
  `convert.py`, `tools.py`, `wheel.py`) has no Qt in it and is tested on its own. The Qt side is
  `radial.py` (the wheel), `editor.py`, `dock.py` (the drop tab), `toasts.py` and `app.py`,
  which ties them together. `glass.py` holds the shared look. Keep conversion out of the UI code
  and drawing out of the logic files.
- Write comments the way you'd explain it to a friend: why, not a line-by-line narration.
- Add a test for new behavior.
- If your change affects what a user sees or types, update the README and the changelog.

## Ideas that would be great

- More formats (images, audio, video, documents, archives).
- Support for more file managers and desktops, with real testing.
- A Windows port.

## License

By contributing you agree that your work is released under the project's license,
GPL-3.0-or-later.
