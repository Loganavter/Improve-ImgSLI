<p align="center">
  <img src="https://raw.githubusercontent.com/johnpetersa19/Improve-ImgSLI/037ab021aa79aa40a85a25d591e887dca85cd50d/src/icons/logo-github%20.svg" alt="Logo" width="384">
</p>

<p align="center">
  <a href="https://github.com/Loganavter/Improve-ImgSLI/releases/latest">
    <img src="https://img.shields.io/github/v/release/Loganavter/Improve-ImgSLI?style=flat-square">

  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/github/license/Loganavter/Improve-ImgSLI?style=flat-square">
  </a>
  <a href="https://github.com/Loganavter/Improve-ImgSLI/releases">
    <img src="https://img.shields.io/github/downloads/Loganavter/Improve-ImgSLI/total?style=flat-square" alt="GitHub Downloads">
  </a>
  <a href="https://flathub.org/apps/details/io.github.Loganavter.Improve-ImgSLI">
    <img src="https://img.shields.io/flathub/downloads/io.github.Loganavter.Improve-ImgSLI?style=flat-square" alt="Flathub Downloads">
  </a>
</p>

<p align="center"><strong>An intuitive, open-source tool for advanced image comparison and interaction.</strong></p>

<p align="center">
  Read this in other languages:
  <a href="README.ru.md">Русский</a>
</p>


---

## 📸 Preview

<div align="center">
   <img width="1920" height="994" alt="Снимок экрана от 2025-10-21 02-47-54" src="https://github.com/user-attachments/assets/3b800ba4-6d37-4a74-aa19-58c2e2ae3ec9" width="75%">
</div>

<details>
  <summary>Full resolution save</summary>
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/1.4/Improve_ImgSLI/fullres/github_fullres.png" alt="Full resolution example" width="33%">
</details>

---

## 🧭 Quick links

- Get Improve-ImgSLI: <a href="https://github.com/Loganavter/Improve-ImgSLI/releases/latest">Windows installer</a> • <a href="https://flathub.org/apps/details/io.github.Loganavter.Improve-ImgSLI">Flathub</a> • <a href="https://aur.archlinux.org/packages/improve-imgsli">AUR</a>
- Install & run from source: <a href="docs/INSTALL.md">docs/INSTALL.md</a>
- Learn the app (Help): <a href="src/resources/help/en/introduction.md">EN Introduction</a> • <a href="src/resources/help/en/">EN All topics</a> • <a href="src/resources/help/ru/">RU Docs</a>
- Contribute: <a href="CONTRIBUTING.md">CONTRIBUTING.md</a>
- More: <a href="HISTORY.md">Development History</a> • <a href="VISION.md">Project Vision</a>

---

## 🚀 Key Features

- 🖼️ Comparison & Viewing: vertical/horizontal split, synced pan/zoom, quick preview with Space + mouse buttons.
- 🔍 Magnifier: dual or split circle, multiple interpolation modes (Nearest, Bilinear, Bicubic, Lanczos), precise WASD/QE controls, freeze position, "laser" guides.
- 🗂️ Workflow & file management: drag-n-drop, reorder across left/right lists, short/long press actions, ratings, filename editing, clipboard paste (Ctrl+V).
- 🎥 Video Recording & Editing: record comparison sessions, basic trimming, and export to popular formats (MP4, WebM, etc.).
- 🎨 Overlays & UI: Fully custom interface with customizable comparison and magnifier dividers (visibility, color, thickness), custom icon buttons, light/dark themes, and custom UI font.
- 📤 Export: WYSIWYG export of the current composite (splitter, magnifier, text), multiple formats (PNG/JPEG/WEBP/BMP/TIFF/JXL), quality controls, text overlays with styling.
- ⚙️ UX & settings: persistent window/layout, multilingual UI (EN/RU/zh/pt_BR), auto-cropping of black borders, robust launcher for venv, debug, profiling.

---

## 🛠 Installation

End users:
- Windows: download and run the latest installer from the <a href="https://github.com/Loganavter/Improve-ImgSLI/releases/latest">Releases</a>.
- Linux (Flatpak): <code>flatpak install io.github.Loganavter.Improve-ImgSLI</code>, then <code>flatpak run io.github.Loganavter.Improve-ImgSLI</code>.
- Linux (AUR): <code>yay -S improve-imgsli</code>.

From source (minimal):
```bash
git clone https://github.com/Loganavter/Improve-ImgSLI.git
cd Improve-ImgSLI
chmod +x launcher.sh
./launcher.sh run
```
See full instructions in <a href="docs/INSTALL.md">docs/INSTALL.md</a>.

---

## 🧪 Basic Usage

1. Start Improve-ImgSLI.
2. Load images via “Add Img(s)” or drag-and-drop. Use Space + Left/Right Mouse for quick single-image preview.
3. Move the split line with the mouse; toggle Horizontal Split if needed.
4. Enable the magnifier, pick interpolation, and adjust zoom/position via sliders or keys.
5. Customize dividers and text, then export the composite image.

For detailed guides, hotkeys, and settings, use the in-app Help (question mark icon) or open:
- EN: <a href="src/resources/help/en/introduction.md">Introduction</a> • <a href="src/resources/help/en/">All topics</a>
- RU: <a href="src/resources/help/ru/introduction.md">Введение</a> • <a href="src/resources/help/ru/">Все разделы</a>

---

## 🤝 Contributing

Contributions are welcome! Please read <a href="CONTRIBUTING.md">CONTRIBUTING.md</a> for development setup, coding guidelines, and packaging notes. Report issues and propose PRs via GitHub.

---

## 🫂 Maintainers

This project is supported and improved by the efforts of dedicated maintainers. A huge thank you for their contributions!

<table>
  <tr>
    <td align="center" valign="top" width="140">
      <a href="https://github.com/nebulosa2007" title="GitHub profile">
        <img src="https://github.com/nebulosa2007.png?size=100" alt="Nebulosa's Avatar" width="100" style="border-radius: 50%;"><br/>
        <sub><b>Nebulosa</b></sub>
      </a>
    </td>
    <td valign="top">
      <strong>AUR Package Maintainer</strong>
      <p>A massive thank you to Nebulosa for his relentless dedication to maintaining the <a href="https://aur.archlinux.org/packages/improve-imgsli">Arch Linux (AUR)</a> package right from the start. His proactive work in fixing packaging issues and ensuring stability has been crucial for the project's presence and reliability within the Arch community.</p>
      <a href="https://github.com/nebulosa2007"><img src="https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub"></a>
      <a href="https://aur.archlinux.org/account/Nebulosa"><img src="https://img.shields.io/badge/AUR-1793D1?style=for-the-badge&logo=arch-linux&logoColor=white" alt="AUR Profile"></a>
    </td>
  </tr>
</table>

---

## 📄 License

MIT License. See <a href="LICENSE">LICENSE</a> for details.

---

## ⭐ Star History

![Star History Chart](https://api.star-history.com/svg?repos=Loganavter/Improve-ImgSLI&type=Timeline)
