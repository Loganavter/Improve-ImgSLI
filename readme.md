<p align="center">
  <img src="https://raw.githubusercontent.com/johnpetersa19/Improve-ImgSLI/037ab021aa79aa40a85a25d591e887dca85cd50d/src/icons/logo-github%20.svg" alt="Logo" width="384">
</p>

<p align="center">
  <a href="https://github.com/Loganavter/Improve-ImgSLI/releases/latest">
    <img src="https://img.shields.io/github/v/release/Loganavter/Improve-ImgSLI?style=flat-square" alt="GitHub release (latest by date)">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/github/license/Loganavter/Improve-ImgSLI?style=flat-square" alt="License: MIT">
  </a>
</p>

<h3 align="center"><em>An intuitive, open-source tool for advanced image comparison and interaction.</em></h3>

---

<p align="center">
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/1.1/Improve_ImgSLI/screenshots/github_1.png" alt="Side-by-side comparison with vertical split" width="32%">
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/1.1/Improve_ImgSLI/screenshots/github_2.png" alt="Magnifying glass tool inspecting details" width="32%">
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/1.1/Improve_ImgSLI/screenshots/github_3.png" alt="Language selection interface" width="32%">
</p>

<details>
  <summary><strong>Full resolution save</strong></summary>
  <p align="center">
    <img src="https://raw.githubusercontent.com/Loganavter/media_archive/1.1/Improve_ImgSLI/fullres/github_fullres.png" alt="Another feature example" width="33%">
  </p>
</details>

---

## 📑 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Installation](#installation)
- [Basic Usage](#basic-usage)
- [Contributing](#contributing)
- [License](#license)
- [Development Story](#development-story)
- [My personal view on project](#my-personal-view)

---

## 📌 Overview <a name="overview"></a>

**Improved ImgSLI** is an open-source, non-proprietary software designed for intuitive image interactions. It's completely free, allowing easy distribution without restrictive licensing. It's built for anyone needing detailed image comparison, analysis, or manipulation — such as designers, upscale enthusiasts, photographers, or researchers.

---

## 🚀 Key Features <a name="key-features"></a>

### 🖼️ Core Comparison & Viewing
- Intuitive image splitting (horizontal/vertical) controlled by mouse.
- Display original resolution (WxH) for each loaded image.
- Automatic resizing of images to match the largest dimensions for consistent comparison.
- Save the current comparison view (including split line, magnifier, capture marker, and optional file names) as a full-resolution image.

### 🔍 Magnifier Tool
- Powerful Magnifier for close inspection.
- Visual marker (red circle) indicating the magnifier's capture area on the main image.
- Adjustable magnification area size and magnifier display size.
- Adjustable movement speed for WASD magnifier control.
- Independent magnifier movement using WASD keys (with smooth interpolation).
- Adjust distance between magnifiers using Q and E keys (with smooth interpolation).
- Option to combine magnifiers for direct comparison of magnified areas.
- Freeze the magnifier's view position.

### 📂 File & Workflow Management
- Drag-and-drop support for loading one or multiple images per panel.
- Select loaded images via dropdown menus when multiple images are loaded into a panel.
- Swap entire image lists between panels with a single button click.
- Clear image lists for each panel individually using Trash (🗑️) buttons.
- Edit image names directly within the application interface.
- Option to include file names in the saved comparison image.
- Customizable font size and color for included file names.
- Adjustable maximum length for displayed file names with visual warnings.

### 🧩 User Experience & Interface
- Multilingual support (English, Russian, Chinese, Brazilian Portuguese) with flag-based language selection.
- Dynamic window resizing with adaptive content rendering (relative coords).
- Persistent settings for window state, language, and various display preferences across sessions.

---

## ⚙️ Installation <a name="installation"></a>

### Python (from source)
Requires: Python, pip, bash

```bash
git clone https://github.com/Loganavter/Improve-ImgSLI.git
cd Improve-ImgSLI
chmod +x launcher.sh
./launcher.sh
```

### Arch Linux (AUR)

```bash
yay -S improve-imgsli
```

### Windows (Inno Setup)
1. Download it from [>>>here<<<](https://github.com/Loganavter/Improve-ImgSLI/releases/download/v3.1.2/Improve_ImgSLI.exe)
2. Run the installer and follow the prompts.

### Flatpak (Flathub)
Requires: Flatpak

```bash
flatpak install io.github.Loganavter.Improve-ImgSLI
flatpak run io.github.Loganavter.Improve-ImgSLI
```

### macOS
Help wanted! We are looking for assistance to create and maintain a macOS build.  
[See the discussion and contribute here](https://github.com/Loganavter/Improve-ImgSLI/pull/15)

---

## 🧪 Basic Usage <a name="basic-usage"></a>

1. **Launch** the app using your installation method.
2. **Load Images** via drag-and-drop or using the "Add Img(s)" buttons.
3. **Compare** using the mouse to control the separator line; use the "Horizontal Split" checkbox for orientation.
4. **Magnify** using the checkbox; WASD controls movement, Q/E controls distance, and Freeze locks view.
5. **Save** with the "Save Result" button to export the comparison as an image.

![Demo](https://github.com/user-attachments/assets/f2c843c2-31eb-4fb9-8eef-2d28630f2baf)

---

## 🤝 Contributing <a name="contributing"></a>

Contributions are welcome! Feel free to:
- Report bugs or suggest features by opening an [Issue](https://github.com/Loganavter/Improve-ImgSLI/issues).
- Submit improvements via a [Pull Request](https://github.com/Loganavter/Improve-ImgSLI/pulls).

---

## 📜 License <a name="license"></a>

This project is licensed under the **MIT License**.  
See the [LICENSE](https://github.com/Loganavter/Improve-ImgSLI/blob/main/LICENSE.txt) file for more information.

---

<p align="center">
  <a href="https://star-history.com/#loganavter/Improve-ImgSLI&Date">
    <img src="https://api.star-history.com/svg?repos=Loganavter/Improve-ImgSLI&type=Date" alt="Star History Chart">
  </a>
</p>

---

<details>
<summary>📖 <strong>Development Story</strong> <a name="development-story"></a></summary>

After encountering countless issues with ImageSplit tools crashing or being buggy, I created this improved version from the ground up. It focuses on image comparison, preserving high-resolution details, and enabling pixel-level analysis with smooth tools.

Everything was crafted with usability in mind — from the intuitive magnifier and marker to dropdown menus and customizable text.

My journey with this tool involved rigorous testing and frequent tweaks to ensure it feels natural to anyone using it — even for the first time. Its performance scales well across systems, making it accessible and lightweight despite being powerful.

</details>

<details>
<summary>💬 <strong>My personal view on project</strong> <a name="my-personal-view"></a></summary>

This is not just a tool; it's something I personally rely on during upscale comparisons or detailed analysis. It began as a side project, but it grew into something that truly reflects my own workflow needs and vision.

If you find this tool useful, please consider giving it a ⭐ star — it helps visibility and motivates me to continue polishing it.

</details>
