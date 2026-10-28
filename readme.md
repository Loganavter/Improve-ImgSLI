<p align="center">
  <img src="src/resources/icons/blinktable-logo.svg" alt="BlinkTable" width="384">
</p>

<h1 align="center">BlinkTable</h1>

<p align="center">
  <a href="https://github.com/Loganavter/Improve-ImgSLI/releases/latest"><img src="https://img.shields.io/github/v/release/Loganavter/Improve-ImgSLI?style=flat-square"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/Loganavter/Improve-ImgSLI?style=flat-square"></a>
  <a href="https://github.com/Loganavter/Improve-ImgSLI/releases"><img src="https://img.shields.io/github/downloads/Loganavter/Improve-ImgSLI/total?style=flat-square" alt="GitHub Downloads"></a>
  <a href="https://flathub.org/apps/details/io.github.Loganavter.Improve-ImgSLI"><img src="https://img.shields.io/flathub/downloads/io.github.Loganavter.Improve-ImgSLI?style=flat-square" alt="Flathub Downloads"></a>
</p>

<p align="center">A desktop workspace for comparing images and video frames.</p>

<p align="center">Read this in other languages: <a href="README.ru.md">Русский</a></p>

## What it is

The app opens on a session picker and runs three kinds of workspace tab. Image
Compare puts two images side by side. Multi Compare synchronizes any number of
images in one scene. Image Gallery triages, measures and scores whole folders.
Each tab has its own canvas, state, help pages and export path.

## Compare

- Split, pan and zoom on the GPU: horizontal or vertical split, synced pan and
  zoom across sides, channel views, fullscreen focus for one cell.
- Magnifiers, dual or combined circle, with their own split control, EWA Lanczos
  sampling, freeze mode and guide lines. Place as many as you need; each keeps
  its own area, position, size and colours.
- Hold <kbd>Space</kbd> with a mouse button to preview a single image.
- Every surface answers the keyboard. WASD and QE navigate,
  <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> opens Find Action, which runs any
  command by name.

## Measure

- Diff modes: highlight, grayscale, edges, SSIM map.
- PSNR and SSIM for each pair of images.
- The AI scorecard sends the compared images to a vision model and returns a
  score per axis plus a verdict; the key goes in Settings → AI. Results are
  cached per backend, so switching the model or the endpoint re-analyses
  instead of showing old scores.
- Ask AI about a card or a selection and the answer stays inside what you
  selected.
- Gallery triage: sort, rank, reject or keep, group series, reset metric caches,
  run Clean Review.

## Export

- Image export writes the composed view: splitters, magnifier, overlays and
  styled file names, as you see them. PNG, JPEG, WEBP, BMP, TIFF, JXL.
- Record a session in the video editor, trim or delete ranges, keyframe states,
  and export MP4, WebM, AVI, GIF, ProRes or AV1.
- Export jobs report progress and cancel without leaving a dead row in the list.

## Workspace

- Tabbed window with a Firefox-style tab bar; the session picker appears on
  start.
- Project files (`.blinktable`; older `.imgsli` projects still open) keep
  images, splitters, magnifiers and video sessions together.
- The interface is drawn by the project's own toolkit, without QSS: light and
  dark themes, custom fonts, and a live UI scale from 0.5 to 2.5× that
  re-derives geometry instead of stretching it.
- English, Russian, Chinese and Brazilian Portuguese; tray integration, save
  notifications, a launcher for source runs, and auto-crop.

## Agent control

A control channel (`BLINKTABLE_CONTROL=1`) and an MCP server expose 23 tools:
inventory elements, read the Store, actions, log and tracer, click, press keys,
walk keyboard sections, list and cancel jobs, set theme or language, capture a
surface, and wait for an asynchronous state instead of polling.

Every result states whether it came from a live instance. Captures report their
method and canvas-layer count, and keyboard reachability is measured
(`ui_nav_state` with `nav_key`). Reference: [docs/dev/MCP.md](docs/dev/MCP.md).

## Install

| Platform | How |
|---|---|
| Windows | latest installer from [Releases](https://github.com/Loganavter/Improve-ImgSLI/releases/latest) |
| Linux (Flatpak) | `flatpak install io.github.Loganavter.Improve-ImgSLI` then `flatpak run io.github.Loganavter.Improve-ImgSLI` |
| Linux (AUR) | `yay -S improve-imgsli` |
| From source | `git clone … && cd Improve-ImgSLI && ./launcher.sh run` |

Full instructions: [docs/INSTALL.md](docs/INSTALL.md) · launcher reference:
[docs/LAUNCHER.md](docs/LAUNCHER.md).

Images above `65536 px` on a side are rejected on the bounded decode path;
streaming decode has no such bound. Still-image export above `16384 px` warns
that the path is untested.

## First five minutes

1. Start the app. The session picker opens; pick Image Compare, Multi Compare or
   Image Gallery, and it becomes its own tab.
2. Press <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd>. Find Action runs any
   command by name, and "Learn more" opens the matching help topic.
3. In Image Compare, add images with the button or by drag and drop. Move the
   split line, zoom with the wheel, then hold <kbd>Space</kbd> with a mouse
   button to preview one side.
4. Open the magnifier, choose an interpolation, adjust the zoom, and export the
   composed view.
5. In the Gallery, point the analysis at a folder: metrics for every pair, and
   the AI scorecard once a key is configured.

Hotkeys, settings and the full workflow live in the in-app Help (Help menu).
Sources: [EN host topics](src/resources/help/en/) · [RU](src/resources/help/ru/) ·
[Image Compare](src/tabs/image_compare/resources/help/en/) ·
[Multi Compare](src/tabs/multi_compare/resources/help/en/) ·
[Gallery](src/tabs/image_gallery/resources/help/en/).

## Docs

| You want | Read |
|---|---|
| Install / launcher | [docs/INSTALL.md](docs/INSTALL.md), [docs/LAUNCHER.md](docs/LAUNCHER.md) |
| Drive the app from an agent | [docs/dev/MCP.md](docs/dev/MCP.md) |
| Contribute / dev setup | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Architecture, contracts, patterns | [docs/dev/ARCHITECTURE.md](docs/dev/ARCHITECTURE.md), [docs/dev/CONTRACTS.md](docs/dev/CONTRACTS.md) |
| Project vision and history | [VISION.md](VISION.md), [docs/DEVELOPMENT_HISTORY.md](docs/DEVELOPMENT_HISTORY.md) |
| Open engineering debt | [docs/dev/TODO.md](docs/dev/TODO.md) |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, coding guidelines and packaging
notes. Issues and pull requests go through GitHub.

## Maintainers

<table>
  <tr>
    <td align="center" valign="top" width="140">
      <a href="https://github.com/nebulosa2007" title="GitHub profile">
        <img src="https://github.com/nebulosa2007.png?size=100" alt="Nebulosa's Avatar" width="100" style="border-radius: 50%;"><br/>
        <sub><b>Nebulosa</b></sub>
      </a>
    </td>
    <td valign="top">
      <strong>AUR package maintainer</strong>
      <p>Nebulosa maintains the <a href="https://aur.archlinux.org/packages/improve-imgsli">Arch Linux (AUR)</a> package and has done since the project started, with packaging fixes and stability work for the Arch ecosystem.</p>
      <a href="https://github.com/nebulosa2007"><img src="https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub"></a>
      <a href="https://aur.archlinux.org/account/Nebulosa"><img src="https://img.shields.io/badge/AUR-1793D1?style=for-the-badge&logo=arch-linux&logoColor=white" alt="AUR Profile"></a>
    </td>
  </tr>
</table>

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). Runtime dependencies, including
PySide6/Qt under LGPL-3.0-or-later, are listed in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

## Star history

![Star History Chart](https://api.star-history.com/svg?repos=Loganavter/Improve-ImgSLI&type=Timeline)
