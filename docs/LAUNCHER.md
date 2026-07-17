# Launcher Guide (`launcher.sh`)

This guide is for end users who run Improve-ImgSLI from source.

Use `launcher.sh` to set up Python dependencies, start the app, run tests, and clean your local environment without manual `venv` steps.

## Quick start

```bash
chmod +x launcher.sh
./launcher.sh run
```

On first run, the launcher creates `venv/`, installs requirements, and starts the app.

## Command overview

Show all commands:

```bash
./launcher.sh help
```

Main commands:

- `./launcher.sh run` - start the app
- `./launcher.sh run --theme dark` - force theme for this session (`dark` or `light`)
- `./launcher.sh run --debug` - enable debug logging for this session
- `./launcher.sh test` - run full pytest suite
- `./launcher.sh install` - create/update virtual environment and dependencies
- `./launcher.sh recreate` - rebuild virtual environment from scratch
- `./launcher.sh rm-cache` - remove Python caches only
- `./launcher.sh delete` - remove virtual environment and caches
- `./launcher.sh install-desktop` - install Linux desktop launcher
- `./launcher.sh uninstall-desktop` - remove Linux desktop launcher

## Logging modes

- `./launcher.sh run --debug` - one-time debug session (recommended for troubleshooting)
- `./launcher.sh --enable-logging` - enable persistent debug logging
- `./launcher.sh --disable-logging` - disable persistent debug logging

Runtime log file:

- `~/.local/share/ImproveImgSLI/log.txt`

## Useful examples

Run one test file:

```bash
./launcher.sh test tests/plugins/test_help_plugin.py -q
```

Run tests by keyword:

```bash
./launcher.sh test -k export -q
```

Get code-size stats (cloc table):

```bash
./launcher.sh context --cloc-only
```

This writes `cloc.txt` in the repository root.

## Troubleshooting

- If startup fails after dependency updates: `./launcher.sh recreate`
- If weird stale behavior persists: `./launcher.sh rm-cache`
- If desktop shortcut is missing on Linux: `./launcher.sh install-desktop`

If problems continue, include:

- launcher command you ran
- terminal output
- `~/.local/share/ImproveImgSLI/log.txt`
