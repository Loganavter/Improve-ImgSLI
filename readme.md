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
</p>

<p align="center"><strong>An intuitive, open-source tool for advanced image comparison and interaction.</strong></p>

---

## 📸 Screenshots

<div align="center">
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/1.3/Improve_ImgSLI/screenshots/github_1.png" width="32%">
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/1.3/Improve_ImgSLI/screenshots/github_2.png" width="32%">
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/1.3/Improve_ImgSLI/screenshots/github_3.png" width="32%">
</div>

<details>
  <summary>Full resolution save</summary>
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/1.1/Improve_ImgSLI/fullres/github_fullres.png" alt="Full resolution example" width="33%">
</details>

---

## 📖 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Installation](#installation)
- [Basic Usage](#basic-usage)
- [Contributing](#contributing)
- [License](#license)
- [Development Story](#development-story)
- [My Personal View](#my-personal-view)

---

## 🧩 Overview <a name="overview"></a>

Improve-ImgSLI is a free and open-source application for detailed visual image comparison — ideal for designers, photographers, upscaling enthusiasts, and researchers.

---

## 🚀 Key Features <a name="key-features"></a>

### 🖼️ Core Comparison & Viewing
- Horizontal/vertical image split with mouse control.
- Original resolution display (WxH).
- Auto-resize to match dimensions.
- Export current view to high-res image (includes divider, magnifier, marker, and filenames).

### 🔍 Magnifier Tool
- Powerful image magnifier tool.
- Selectable interpolation method (Nearest Neighbor, Bilinear, Bicubic, Lanczos).
- Marker showing the captured area.
- Adjustable source size and magnified area.
- Smooth WASD controls for magnifier movement.
- Merge both magnifiers into one view.
- Freeze magnifier position.

### 🗂️ File & Workflow Management
- Drag and drop multiple files.
- Dropdowns to select from loaded images.
- Quick switch between image lists.
- Clear list buttons.
- Filename editing from UI.
- Optional filename overlay in exports.
- Customizable font and max name length.

### 🧑‍💻 User Experience & Interface
- Multilingual support (EN, RU, ZH, PT-BR).
- Dynamic UI resizing.
- Settings persist across sessions.
- Quick image preview using keyboard (Space + Mouse Buttons).
- Improved performance through advanced image caching.

---

## 🛠️ Installation <a name="installation"></a>

### 🐍 Python (from source)
```bash
git clone https://github.com/Loganavter/Improve-ImgSLI.git
cd Improve-ImgSLI
chmod +x launcher.sh
./launcher.sh
```

### 🐧 Arch Linux (AUR)
```bash
yay -S improve-imgsli
```

### 🪟 Windows (Inno Setup)
1. Download the installer [here](https://github.com/Loganavter/Improve-ImgSLI/releases/download/v4.9.0/Improve_ImgSLI_Setup_v4.9.0.exe)
2. Run and install normally

### 🧊 Flatpak (Flathub)
```bash
flatpak install io.github.Loganavter.Improve-ImgSLI
flatpak run io.github.Loganavter.Improve-ImgSLI
```

### 🍏 macOS
🚧 Help wanted! Contribute to the macOS build [here](https://github.com/Loganavter/Improve-ImgSLI/pull/15).

---

## 🧪 Basic Usage <a name="basic-usage"></a>

1. **Start** Improve-ImgSLI using your preferred installation method.
2. **Load Images** via the "Add Img(s)" button or drag-and-drop. Use Space + Mouse Buttons for quick preview of individual images.
3. **Compare:** move the split line with your mouse. Check "Horizontal Split" to change orientation.
4. **Magnify:** enable the magnifier, select an interpolation method, and adjust zoom/position with sliders or keys.
5. **Export:** use the save button to export a high-res composite.

https://github.com/user-attachments/assets/f2c843c2-31eb-4fb9-8eef-2d28630f2baf

---


## 🤝 Contributing <a name="contributing"></a>

Feel free to fork, submit [issues](https://github.com/Loganavter/Improve-ImgSLI/issues), or open [PRs](https://github.com/Loganavter/Improve-ImgSLI/pulls). Contributions are welcome!
<details>
  
<summary>Best Contributors</summary>

Special thanks to [Anduin9527](https://github.com/Anduin9527)! I borrowed many GUI developments from his [fork](https://github.com/Anduin9527/Improve-ImgSLI) of this project.
Special thanks to [johnpetersa19](https://github.com/johnpetersa19)! Your [reworking](https://github.com/Loganavter/Improve-ImgSLI/pull/18) of Readme.MD greatly improved the look of the project with a bunch of contextual emoji.
</details>

---

## 📄 License <a name="license"></a>

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## 🧠 Development Story <a name="development-story"></a>

<details>
<summary>Development Story</summary>
The journey of Improve ImgSLI began in September 2024, initially conceived with ChatGPT's assistance to address a personal need for straightforward image comparison in my work. The early version provided basic side-by-side functionality. The following month, October, marked an enhancement phase using Claude, which introduced a magnifier tool and drag-and-drop support, significantly improving usability.

By November, further refinements to the magnifier were implemented with Claude, including view freezing and merging capabilities. However, the codebase's expansion, coupled with Claude's 8k token context limit, made complete code regeneration impractical, necessitating manual integration of new features. Gemini was then employed to help manage these integrations, though not all AI-generated code was directly usable, leading to some features being postponed or temporarily disabled to maintain stability.

A brief period in early December saw an experiment with adaptive magnifier positioning tied to window resizing, which was ultimately set aside due to unsatisfactory results. A turning point came in January 2025 when a user [request](https://github.com/Loganavter/Improve-ImgSLI/issues/1) for dynamic window resizing led to the exploration of DeepSeek. This AI, notable at the time for its Chain-of-Thought reasoning, successfully guided the implementation of this crucial feature, with Gemini then seamlessly incorporating it alongside other updates.

February 2025 brought renewed focus on enhancing the application. Leveraging Claude Sonnet 3.7, features like dynamic image swapping, a multilingual dictionary, and further magnifier improvements were added, along with a helpful tooltip. Shortly thereafter, access to Grok 3—first via X, then its dedicated website—provided a significant boost. Grok 3's DeepThink model proved exceptionally effective at resolving persistent bugs, outperforming previous AIs, while its generous query limits and intelligent standard model streamlined development. Key contributions included optimized rendering, filename display and editing, and fixes for fullscreen mode.

Late March 2025 was dedicated to cross-platform compatibility. Gemini and Grok, using their web search capabilities, assisted in drafting build and packaging scripts. While initial hopes for community maintenance of platform builds didn't materialize due to some skepticism about the project's AI-assisted origins, this solo effort, though time-intensive (taking considerable effort per platform), led to the discovery and resolution of several bugs, culminating in a successful cross-platform launch. Delays in Flathub publication until mid-April allowed for further bug fixes and the addition of a list cleanup feature.

In April 2025, attention shifted back to addressing critical bugs, with continued reliance on Gemini. A major achievement during this period was the implementation of window state persistence—a feature that proved incredibly challenging but vastly improved user experience. A settings tab was also introduced, centralizing language selection, output image quality, and filename length preferences. Following these updates, Windows and Flatpak builds were refreshed. The current plan involves implementing one final feature and verifying the Flatpak maintenance pipeline before updating Windows and AUR builds, after which the project will likely enter a period of stability.

May 2025. I discovered Cursor AI, which allowed me to quickly implement three key features in this update using agents like ChatGPT 4.1, Sonnet 3.5, and Gemini 2.5 PRO, all within the free limit of 150 uses. These features included a smarter caching service that improved smoothness by approximately 2-3 times compared to the previous version, the ability to select magnifier interpolation, and quick image preview using the keyboard. Additionally, the project's structure became much more multi-layered and less coupled between modules. This refactoring required two days of collaboration with Gemini to break down two monolithic scripts into numerous services with separate folders. The entire process took about three days.

June 2025. With Gemini, I refactored the code once again. The application now features a qfluentwidgets style. This was quite a time-consuming process. Caching was also further improved. The icons.py file was completely removed as it was no longer necessary.
</details>

---

## 💬 My Personal View <a name="my-personal-view"></a>

<details>
<summary>My personal view on project<a name="my-personal-view"></summary>
The genesis of Improve ImgSLI was a practical need: to create clear visual comparisons for an article. The initial design, and indeed the name, drew inspiration from imgsli.com. While the early iterations were functional, the project has since evolved significantly.

Today, I view Improve ImgSLI as a valuable public asset, much like [VideoCut](https://github.com/kanehekili/VideoCut) Kanehekili, another tool whose principles partially guided its development and which has become indispensable in my own workflow. The core value of Improve ImgSLI lies in its efficiency. Manually creating detailed image comparisons can be a laborious process, often taking several minutes. This program accomplishes the same, often superior, results in approximately 30 seconds, all through an intuitive, user-friendly interface. It's this transformation of a cumbersome task into a swift, accessible one that I believe makes Improve ImgSLI a genuinely useful tool.
</details>

---

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Loganavter/Improve-ImgSLI&type=Timeline)](https://star-history.com/#Loganavter/Improve-ImgSLI&Timeline)
