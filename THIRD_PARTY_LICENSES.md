# Third-Party Licenses

Improve-ImgSLI application source code is licensed under **GPL-3.0-or-later**.
See [LICENSE](LICENSE).

This document lists major runtime and bundled dependencies and the license
obligations that apply when you distribute Improve-ImgSLI binaries.

---

## PySide6, shiboken6, and Qt 6 (LGPL-3.0-or-later)

Improve-ImgSLI uses **Qt for Python (PySide6)** and **shiboken6**, which link
against **Qt 6**. These components are licensed under the **GNU Lesser General
Public License v3.0 or later (LGPL-3.0-or-later)**.

- PySide6 project: https://doc.qt.io/qtforpython/
- Qt 6 source archives: https://download.qt.io/official_releases/qt/
- LGPL-3.0 text: https://www.gnu.org/licenses/lgpl-3.0.html

### LGPL compliance notes for binary distributions

When Improve-ImgSLI is distributed as a standalone bundle (for example the
Windows PyInstaller directory layout):

1. Qt libraries are shipped as separate `.dll` / `.pyd` files under the
   `PySide6\` directory (not statically linked into a single opaque binary).
2. You may replace those Qt/PySide6 library files with your own LGPL-compliant
   builds of the same major Qt version, provided the replacement remains
   interface-compatible.
3. Corresponding source code for the Qt version used in the bundle is available
   from The Qt Company / Qt Project at the URL above.
4. Windows builds also ship:
   - `licenses\WINDOWS_QT_NOTICE.txt` — replacement instructions
   - `licenses\LGPL-3.0.txt` — full LGPL text
   - `licenses\Qt_BUNDLE_INFO.txt` — PySide6/Qt version and file list (generated at build time)
5. The Windows installer shows the GPL application license and the Qt notice
   during setup (`build/Windows-template/inno_setup_6.iss`).

Linux packages (AUR, Flatpak) typically obtain PySide6/Qt from the
distribution runtime or system packages; refer to those packages for their
LGPL source offers.

---

## sli-ui-toolkit (MIT)

The reusable UI widget library **sli-ui-toolkit** (`sli_ui_toolkit` Python
package) is bundled or installed alongside Improve-ImgSLI and is licensed
under the **MIT License**.

- Repository: https://github.com/Loganavter/sli-ui-toolkit

---

## Other Python runtime dependencies

The following libraries are commonly used at runtime. Each is governed by its
own license (typically permissive). Source and license texts are available from
PyPI and the respective project repositories.

| Component | Typical license | Notes |
|-----------|-----------------|-------|
| Pillow | MIT-CMU / PIL license | Image I/O |
| NumPy | BSD-3-Clause | Numerical arrays |
| scikit-image | BSD-3-Clause | SSIM and image metrics |
| imagecodecs | BSD-3-Clause | Optional JXL and codec support |
| Markdown | BSD-3-Clause | In-app help rendering |
| PyOpenGL | BSD-3-Clause | Legacy OpenGL helpers (where used) |

---

## FFmpeg (external, Flatpak extension)

The Flatpak build may use the `org.freedesktop.Platform.ffmpeg-full` runtime
extension for video export. FFmpeg is licensed under **LGPL-2.1-or-later**
and/or **GPL-2.0-or-later** depending on build configuration. See the Flatpak
runtime documentation and FFmpeg project for details.

---

## Questions

For licensing questions about Improve-ImgSLI itself, see [LICENSE](LICENSE) and
the project homepage: https://github.com/Loganavter/Improve-ImgSLI

This file is provided for attribution and compliance convenience. It is not
legal advice.
