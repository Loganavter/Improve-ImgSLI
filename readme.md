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

<p align="center">A desktop app for comparing images and video frames.</p>

<p align="center">Read this in other languages: <a href="README.ru.md">Русский</a></p>

<p align="center">
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/main/Improve_ImgSLI/screenshots/readme/image-compare.png" alt="Image Compare with the magnifier: a sharp source against the upscaled blocks">
</p>

## What it is

BlinkTable opens on a session picker and gives you independent workspace tabs:
a two-image Image Compare, a synchronized N-image Multi Compare, and an AI
Gallery for triaging, measuring and AI-scoring whole folders. Several workspaces
stay open at once, and each tab keeps its own images, zoom and help.

<p align="center">
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/main/Improve_ImgSLI/screenshots/readme/session-picker.jpg" alt="Session picker with the three session types">
</p>

## Overview

For retouching, upscaling QA and photography, where the comparison itself is
what you deliver. It opens images at enormous megapixel resolutions without lag.

Below, the app's individual tabs.

**Image Compare** puts two images side by side behind one divider. Magnifiers
are separate objects: several at once, each with its own area, zoom and colours.
A comparison can be saved as a full-resolution image, or recorded in the app and
trimmed in the built-in mini video editor.

**AI Gallery** does a lot of the work of comparing large series for you,
quickly: local algorithms or an AI model over OpenRouter judge the shots, and the
interface lets you move through the gallery without waiting.

<p align="center">
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/main/Improve_ImgSLI/screenshots/readme/ai-gallery.jpg" alt="AI Gallery with a folder of shots ranked in a grid">
</p>

**Multi Compare** is a convenient grid for comparing more than two images at
once, dozens and up to hundreds, with one shared zoom and pan for the whole grid
and slots you can drag.

## Agent control

An AI agent can drive a running window and read what is in it: open a tab, take
a comparison apart, capture a surface. Start the app with `BLINKTABLE_CONTROL=1`
so it can connect, then ask in plain words.

Reference: [docs/dev/MCP.md](docs/dev/MCP.md).

## Install

| Platform | How |
|---|---|
| Windows | Installer from [Releases](https://github.com/Loganavter/Improve-ImgSLI/releases/latest) |
| Linux (Flatpak) | `flatpak install io.github.Loganavter.Improve-ImgSLI`, then `flatpak run io.github.Loganavter.Improve-ImgSLI` |
| From source | `git clone … && cd Improve-ImgSLI && ./launcher.sh run` |

Details: [docs/INSTALL.md](docs/INSTALL.md), [docs/LAUNCHER.md](docs/LAUNCHER.md).

## Limits

Images above `65536 px` on a side open only when the format can be read in a
stream; otherwise the decoder stops at that size.

## Documentation

| Topic | Where |
|---|---|
| Install, launcher | [docs/INSTALL.md](docs/INSTALL.md), [docs/LAUNCHER.md](docs/LAUNCHER.md) |
| Controlling the app from an agent | [docs/dev/MCP.md](docs/dev/MCP.md) |
| Development setup | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Architecture and contracts | [docs/dev/ARCHITECTURE.md](docs/dev/ARCHITECTURE.md), [docs/dev/CONTRACTS.md](docs/dev/CONTRACTS.md) |
| Vision and history | [VISION.md](VISION.md), [docs/DEVELOPMENT_HISTORY.md](docs/DEVELOPMENT_HISTORY.md) |
| Open engineering debt | [docs/dev/TODO.md](docs/dev/TODO.md) |

## Contributing

Setup, coding guidelines and packaging notes are in [CONTRIBUTING.md](CONTRIBUTING.md). Issues and pull requests go through GitHub.

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
      <p>Maintains the <a href="https://aur.archlinux.org/packages/improve-imgsli">Arch Linux (AUR)</a> package since the start of the project.</p>
      <a href="https://github.com/nebulosa2007"><img src="https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub"></a>
      <a href="https://aur.archlinux.org/account/Nebulosa"><img src="https://img.shields.io/badge/AUR-1793D1?style=for-the-badge&logo=arch-linux&logoColor=white" alt="AUR Profile"></a>
    </td>
  </tr>
</table>

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). Runtime dependencies, including PySide6/Qt under LGPL-3.0-or-later, are listed in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

## Star history

![Star History Chart](https://api.star-history.com/svg?repos=Loganavter/Improve-ImgSLI&type=Timeline)
