# Release checklist (11.0.0 and later)

Where every version string lives, what must be regenerated, and what can only
be finished **after** the tag and the toolkit upload exist. Local gates are
authoritative here: CI is the backstop, not the feedback loop.

## 1. Version sources (all must agree)

| Surface | File | 11.0.0 value |
|---|---|---|
| Runtime / window / reports | `src/core/constants.py` (`APP_VERSION`) | `11.0.0` |
| Flatpak metainfo (newest `<release>`) | `build/Flatpak-template/io.github.Loganavter.Improve-ImgSLI.metainfo.xml` | `11.0.0` + **today's** date (Moscow) |
| AUR package | `build/AUR-template/PKGBUILD` (`pkgver`) | `11.0.0` |
| Windows installer | `build/Windows-template/inno_setup_6.iss` (`#define MyAppVersion`) | `11.0.0` |
| Windows setup exe name | `build/Windows-template/build_windows.py` | `Improve_ImgSLI_Setup_v11.0.0.exe` |
| Flatpak source archive | `build/Flatpak-template/io.github.Loganavter.Improve-ImgSLI.yaml` | `Improve-ImgSLI-11.0.0.tar.gz` |
| Toolkit pin (Flatpak) | `build/Flatpak-template/python3-modules.json` | `sli-ui-toolkit==4.0.0` |
| Toolkit floor (AUR) | `build/AUR-template/PKGBUILD` (`python-sli-ui-toolkit>=`) | `>=4.0.0` |
| Changelog | `CHANGELOG.md` | `## [11.0.0] — <date>` |

Gate: `python3 build/ci/validate_release_metadata.py` (version agreement,
metainfo date, AUR floor vs Flatpak pin) and
`python3 build/ci/validate_license_files.py`.

## 2. Pre-tag gates (local)

```bash
python3 build/ci/validate_release_metadata.py
python3 build/ci/validate_license_files.py
./launcher.sh test tests/contracts -q
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 ./venv/bin/python -m pytest -q -p no:cacheprovider tests/plugins tests/runtime
python3 src/devtools/docs_link_graph.py --write-index     # docs moved/added
python3 scripts/generate_llms.py                          # help/README copy changed
python3 scripts/check_comment_citations.py
```

## 3. Release order (the toolkit first)

1. **Toolkit** (`sli-ui-toolkit`) tag + PyPI upload of **exactly** the artifact
   the Flatpak manifest pins. The manifest's `sha256` is the hash of that file;
   rebuilding the sdist changes it, so upload the file that was hashed (or
   re-pin it, see §4).
2. **App** `v11.0.0` tag → `updpkgsums` in `build/AUR-template/PKGBUILD`
   (the first sum is the GitHub tag archive and cannot be computed before the
   tag exists) → AUR push → GitHub release.
3. Flatpak: build + submit with the pinned toolkit sdist (§4).

## 4. Flatpak: toolkit sdist pin

`python3-modules.json` installs `sli-ui-toolkit` from the PyPI sdist. The
current entry uses a stable alias URL
(`.../packages/source/s/sli-ui-toolkit/sli_ui_toolkit-4.0.0.tar.gz`) and the
`sha256` of the locally built `sli_ui_toolkit-4.0.0.tar.gz`
(`b1dce408…dfde`, artifact kept at
`~/.cache/opencode/release-artifacts/sli_ui_toolkit-4.0.0.tar.gz`).
If the uploaded artifact differs, re-pin both URL and hash:

```bash
sha256sum sli_ui_toolkit-4.0.0.tar.gz   # then edit the entry
```

Verify in a real build (cannot be done from a source checkout):

- `python3 -c "import torch, torchvision, piq"` inside the sandbox — the CPU
  wheels need `libgomp`; if the runtime lacks it, add the dependency or use the
  platform's OpenMP.
- Launch the app and check `Image Gallery → ranking` reports **AI/metrics**
  rather than the explicit `missing` backend state.

## 5. Windows: learned-metrics backend is bundled

`Improve_ImgSLI.spec` collects `torch`, `torchvision`, `piq` when they are
installed (`collect_all`), so the installer carries the metrics backend
instead of degrading it. Consequences to check on a real Windows build:

- installer size grows by the CPU wheels (~hundreds of MB);
- `build/ci/validate_license_files.py --windows-bundle dist/Improve_ImgSLI`
  still passes (Qt files replaceable, license bundle present).

## 6. Known manifest drifts (not fixed here — need a real build)

`python3-modules.json` versions vs `requirements-gui.txt` / the dev venv:

| Module | Manifest | Dev venv | Action |
|---|---|---|---|
| pillow | 11.2.1 | 12.1.1 | bump + re-pin hash when the Flatpak build can be verified |
| numpy | 2.3.4 | 2.3.5 | within `requirements-gui` range; bump together with scipy/scikit-image |
| scipy | 1.16.0 | 1.18.0 | transitive; bump with the numpy/scikit-image group |
| scikit-image | 0.26.0 | 0.26.0 | in sync |
| imagecodecs | 2026.3.6 | 2026.6.26 | bump + re-pin hash |
| Markdown | 3.8.1 | 3.8 | pin drift only, functionally identical |

Regenerate the whole file with `flatpak-pip-generator` from
`requirements-gui.txt` when the versions are bumped; do not hand-edit hashes.

## 7. Branding (display name only)

The product name is `BlinkTable`; `Improve-ImgSLI` stays the technical identity
(app-id, AUR `pkgname`, MIME type, `StartupWMClass`, Inno Setup identity,
`QSettings` organization/application keys, repository, domain). Rationale and
the exact file list: internal-docs
`docs/dev/investigations/plan-app-branding-2026-10-21.md` (L1/L2 split).

Do **not** rename the app-id or the package inside a release: it resubmits the
listing, orphans the AUR package and moves user settings.

The logo's master file is `src/resources/icons/blinktable-logo.svg`. Anything
derived from the mark is regenerated, never hand-edited:

```bash
rsvg-convert -w 512 -h 512 src/resources/icons/blinktable-logo.svg -o src/resources/icons/icon.png
cp src/resources/icons/icon.png build/Flatpak-template/icon.png
# Windows app icon (16-256) from the same PNG (Pillow), then the MIME icons +
# the .imgsli document icon, which are painted from icon.png:
QT_QPA_PLATFORM=offscreen python3 build/linux/icons/render_mime_icons.py
```
