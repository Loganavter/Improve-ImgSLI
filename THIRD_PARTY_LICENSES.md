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
| SciPy | BSD-3-Clause | `scikit-image` runtime dependency (not build-only) |
| imagecodecs | BSD-3-Clause | Optional JXL and codec support |
| Markdown | BSD-3-Clause | In-app help rendering |
| PyOpenGL | BSD-3-Clause | Legacy OpenGL helpers (where used) |
| pybind11 | BSD-3-Clause | Build dependency of NumPy/SciPy/scikit-image; installed into the Flatpak sandbox prefix |
| pythran | BSD-3-Clause | Build dependency of SciPy/scikit-image; installed into the Flatpak sandbox prefix |
| meson-python | MIT | Build backend for NumPy/SciPy/scikit-image; installed into the Flatpak sandbox prefix |
| poetry-core | MIT | Build backend used while resolving/building the above; installed into the Flatpak sandbox prefix |

---

## OpenBLAS (Flatpak build dependency, BSD-3-Clause)

The Flatpak build compiles **OpenBLAS** from source as the BLAS/LAPACK
backend for NumPy and scikit-image inside the Flatpak sandbox (no system
BLAS is available there). It is licensed under the **BSD-3-Clause License**,
which is compatible with GPL-3.0-or-later. BSD-3-Clause requires
redistributions in binary form to reproduce the copyright notice, this list
of conditions, and the disclaimer "in the documentation and/or other
materials provided with the distribution" — a link alone doesn't satisfy
that, so the full text (copied verbatim from OpenBLAS's own `LICENSE` file,
same notice NumPy's own binary wheels bundle for the identical reason) is
reproduced below.

- Project: https://github.com/OpenMathLib/OpenBLAS

```
Copyright (c) 2011-2014, The OpenBLAS Project
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

   1. Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer.

   2. Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in
      the documentation and/or other materials provided with the
      distribution.
   3. Neither the name of the OpenBLAS project nor the names of
      its contributors may be used to endorse or promote products
      derived from this software without specific prior written
      permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE
USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

OpenBLAS also bundles a reference LAPACK implementation under a closely
related BSD-style notice:

```
LAPACK (bundled in OpenBLAS)
Copyright (c) 1992-2013 The University of Tennessee and The University
                        of Tennessee Research Foundation.  All rights
                        reserved.
Copyright (c) 2000-2013 The University of California Berkeley. All
                        rights reserved.
Copyright (c) 2006-2013 The University of Colorado Denver.  All rights
                        reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

- Redistributions of source code must retain the above copyright
  notice, this list of conditions and the following disclaimer.

- Redistributions in binary form must reproduce the above copyright
  notice, this list of conditions and the following disclaimer listed
  in this license in the documentation and/or other materials
  provided with the distribution.

- Neither the name of the copyright holders nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

Not applicable to the AUR build (uses the system `python-numpy` package,
which pulls its own BLAS backend via Arch's own packaging) or the Windows
build (uses prebuilt NumPy/scikit-image wheels, which already bundle their
own BLAS attribution).

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
