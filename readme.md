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

---

## 📸 Screenshot

<div align="center">
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/1.5/Improve_ImgSLI/screenshots/screenshot_1.png" width="75%">
</div>

<details>
  <summary>Full resolution save</summary>
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/1.4/Improve_ImgSLI/fullres/github_fullres.png" alt="Full resolution example" width="33%">
</details>

---

## 📖 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Installation](#installation)
- [Basic Usage](#basic-usage)
- [Contributing](#contributing)
- [Maintainers](#maintainers)
- [License](#license)
- [Development Story](#development-story)
- [My Personal View](#my-personal-view)

---

## 🧩 Overview <a name="overview"></a>

Improve-ImgSLI is a free and open-source application for detailed visual image comparison — ideal for designers, photographers, upscaling enthusiasts, and researchers.

---

## 🚀 Key Features <a name="key-features"></a>

### 🖼️ Core Viewing & Comparison
- **Dual View Modes**: Side-by-side (vertical) and over-under (horizontal) comparison with a smooth, draggable splitter.
- **Synchronized Interaction**: Pan and zoom actions are perfectly synced across both images for precise analysis.
- **Quick Preview**: Hold `Space` and use the `Left/Right Mouse Buttons` to instantly view the original Image 1 or Image 2 in full.
- **Performance Caching**: Features a configurable display cache resolution (e.g., 4K, 2K, 1080p) to ensure smooth performance even with very large images, while always using original quality for the magnifier and final export.

### 🔍 Advanced Magnifier Tool
- **Flexible Display**: View magnified areas in either a dual-circle (one for each image) or a combined split-circle view.
- **High-Quality Zoom**: Choose from multiple interpolation methods (`Nearest Neighbor`, `Bilinear`, `Bicubic`, `Lanczos`) to control rendering quality.
- **Unclipped Rendering**: The magnifier can be moved freely across the entire view, even beyond the image boundaries, without being cut off.
- **Precise Control**: Fine-tune the zoom level, capture area size, and magnifier position with dedicated sliders and smooth `WASD`/`QE` keyboard controls.
- **Freeze Position**: Lock the magnifier's on-screen position so that they do not shift during the positioning of the detection area.

### 🗂️ Powerful File & Workflow Management
- **Versatile Loading**: Load images via file dialogs or by dragging and dropping multiple files directly into the application.
- **Full List Control**:
    - **Drag & Drop Reordering**: Reorder images within a list or move them between the left and right lists simply by dragging.
    - **Advanced Actions**: Use short-press and long-press actions on `Swap (⇄)` and `Clear (🗑️)` buttons for rapid workflow adjustments.
    - **Image Rating**: Assign ratings to images using `[+]` and `[-]` buttons to help with sorting and selection.
- **Easy Navigation**: Quickly switch between loaded images using scrollable dropdowns.
- **In-UI Editing**: Edit filenames directly within the interface for cleaner exports and better organization.

### 📤 Comprehensive Exporting
- **What You See Is What You Get**: Export the current composite view—including the splitter, magnifier, and text overlays—to a single high-resolution image file.
- **Advanced Options**:
    - **Format Choice**: Save in multiple formats like `PNG`, `JPEG`, `WEBP`, `BMP`, and `TIFF`.
    - **Quality Control**: Adjust JPEG quality and PNG compression levels.
    - **Custom Background**: Optionally fill transparent areas with a color of your choice using a color picker.
- **Customizable Text Overlays**:
    - Control font size, weight, and color.
    - Add a text background with adjustable color and opacity.
    - Choose text placement: either at the image edges or near the split line.

### 🧑‍💻 User Experience & Customization
- **Theme Support**: Automatically adapts to your system's theme, or manually select **Light** or **Dark** mode.
- **Customizable UI Font**: Use the built-in font, your system's default, or select any custom font installed on your system.
- **Persistent State**: The application remembers window size, position, and layout between sessions.
- **Multilingual Interface**: Supports English, Russian, Chinese, and Brazilian Portuguese.
- **Robust Launcher**: A powerful `launcher.sh` script for managing the virtual environment, installing dependencies, running in debug mode, and profiling performance.

---

## 🛠️ Installation <a name="installation"></a>

### 🐍 Python (from source)
A command-line utility for managing the environment.
```bash
git clone https://github.com/Loganavter/Improve-ImgSLI.git
cd Improve-ImgSLI
chmod +x launcher.sh
./launcher.sh run
```
Use `./launcher.sh --help` to see other commands like `recreate`, `delete`, and `enable-logging`.

### 🐧 Arch Linux (AUR)
```bash
yay -S improve-imgsli
```

### 🪟 Windows (Inno Setup)
**Option 1: Pre-built Installer**
1. Download the latest installer from the [Releases page](https://github.com/Loganavter/Improve-ImgSLI/releases/tag/v6.2.0).
2. Run the downloaded `.exe` file and follow the installation instructions.

### Step-by-Step Guide

**Option 2: Build from Source**
If you prefer to compile the application yourself, please follow the detailed instructions. This guide ensures a clean, isolated build environment.
<details>
<summary>Building from Source</summary>

### Prerequisites
- **Python**: Make sure Python is installed. During installation, check the box that says "Add Python to PATH".
- **Git**: Required for cloning the repository.
- **Inno Setup**: Required for creating the final installer package.

### Step-by-Step Guide

1.  **Clone the repository and navigate into it:**
    ```bash
    git clone https://github.com/Loganavter/Improve-ImgSLI.git
    cd Improve-ImgSLI
    ```

2.  **Create and activate a virtual environment:**
    This creates an isolated environment for the project's dependencies, preventing conflicts with other Python projects on your system.
    ```bash
    python -m venv venv
    .\venv\Scripts\activate
    ```
    You should see `(venv)` appear at the beginning of your command prompt line.

3.  **Install dependencies:**
    This will install all required Python packages, including `pyinstaller`, into your active virtual environment.
    ```bash
    pip install -r requirements.txt pyinstaller
    ```

4.  **Create the executable with PyInstaller:**
    Run the following command from the root directory of the project. This command analyzes your project and creates a file named `Improve_ImgSLI.spec`, which stores the build configuration.
    ```bash
    python -m pyinstaller build/Windows-template/Improve_ImgSLI.spec
    ```

5.  **Compile the installer with Inno Setup:**
    - Open the **Inno Setup Compiler**.
    - Go to `File > Open...` and select the script `build/Windows-template/inno_setup_6.iss`.
    - Compile the script by pressing **F9** or using the `Build > Compile` menu.

6.  **Find the result:**
    The final installer, `Improve_ImgSLI_Setup_vX.X.X.exe`, will be created in the `build/Windows-template/Output` directory. You can now use this file to install the application.
</details>

### 🧊 Flatpak (Flathub)
```bash
flatpak install io.github.Loganavter.Improve-ImgSLI
flatpak run io.github.Loganavter.Improve-ImgSLI
```

### 🍏 macOS
🚧 Help wanted! Contribute to the macOS build [here](https://github.com/Loganavter/Improve-ImgSLI/pull/15).

---

## 🫂 Maintainers <a name="maintainers"></a>

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

## 🧪 Basic Usage <a name="basic-usage"></a>

1. **Start** Improve-ImgSLI using your preferred installation method.
2. **Load Images** via the "Add Img(s)" button or drag-and-drop. Use Space + Mouse Buttons for quick preview of individual images.
3. **Compare:** move the split line with your mouse. Check "Horizontal Split" to change orientation.
4. **Magnify:** enable the magnifier, select an interpolation method, and adjust zoom/position with sliders or keys.
5. **Manage Lists:** Use short/long presses on the swap (⇄) and clear (🗑️) buttons for quick workflow.
6. **Export:** use the save button to export a high-res composite.

---

## 🤝 Contributing <a name="contributing"></a>

Feel free to fork, submit [issues](https://github.com/Loganavter/Improve-ImgSLI/issues), or open [PRs](https://github.com/Loganavter/Improve-ImgSLI/pulls). Contributions are welcome!
<details>
  
<summary>Best Contributors</summary>

*   Special thanks to [Anduin9527](https://github.com/Anduin9527)! I borrowed many GUI developments from his [fork](https://github.com/Anduin9527/Improve-ImgSLI) of this project.
*   Special thanks to [johnpetersa19](https://github.com/johnpetersa19)! Your [reworking](https://github.com/Loganavter/Improve-ImgSLI/pull/18) of readme.md greatly improved the look of the project with a bunch of contextual emoji.
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

Late March 2025 was dedicated to cross-platform compatibility. Gemini and Grok, using their web search capabilities, assisted in drafting build and packaging scripts. While initial hopes for community maintenance of platform builds didn't materialize due-to some skepticism about the project's AI-assisted origins, this solo effort, though time-intensive (taking considerable effort per platform), led to the discovery and resolution of several bugs, culminating in a successful cross-platform launch. Delays in Flathub publication until mid-April allowed for further bug fixes and the addition of a list cleanup feature.

In April 2025, attention shifted back to addressing critical bugs, with continued reliance on Gemini. A major achievement during this period was the implementation of window state persistence—a feature that proved incredibly challenging but vastly improved user experience. A settings tab was also introduced, centralizing language selection, output image quality, and filename length preferences. Following these updates, Windows and Flatpak builds were refreshed. The current plan involves implementing one final feature and verifying the Flatpak maintenance pipeline before updating Windows and AUR builds, after which the project will likely enter a period of stability.

May 2025. I discovered Cursor AI, which allowed me to quickly implement three key features in this update using agents like ChatGPT 4.1, Sonnet 3.5, and Gemini 2.5 PRO, all within the free limit of 150 uses. These features included a smarter caching service that improved smoothness by approximately 2-3 times compared to the previous version, the ability to select magnifier interpolation, and quick image preview using the keyboard. Additionally, the project's structure became much more multi-layered and less coupled between modules. This refactoring required two days of collaboration with Gemini to break down two monolithic scripts into numerous services with separate folders. The entire process took about three days.

June 2025. With Gemini, I refactored the code once again. The application now features a qfluentwidgets style. It initially took a long time, but then I gave the project fork code with this GUI, and it went much faster, it took about 3 days. Caching was also further improved. The icons.py file was completely removed as it was no longer necessary.

July 2025. The solid architecture from the June refactoring allowed for another rapid development burst. This update took about 4-5 days, again with Gemini's assistance. The launcher.sh script was turned into a proper command-line utility for managing the environment. The rendering pipeline was overhauled to use a dynamic canvas, which allows the magnifier to draw outside the image bounds and also improves performance on large images and magnifiers due to more efficient data packaging. The magnifier also now correctly handles horizontal splitting. UI interaction was improved with long-press actions and scrollable selection dropdowns. Internally, all print statements were replaced with a standard logging system. The persistent bug with window geometry, however, remains. After over 20 failed attempts to fix it, it's clear the root cause is a race condition in how state signals are handled. This confirms the need to move away from the current semblance of an architecture to a **full** MVC/MVVM pattern, which will be the primary focus going forward.

August 2025. This update was born out of necessity. The qfluentwidgets library, while initially useful, became a major roadblock due to its extreme rigidity in customization. Discovering that simple layout logic was hardcoded in its C++ source was the final straw. This prompted a full rewrite of the user interface with 100% custom components. In parallel, the long-standing "god script" issue was tackled by migrating the entire application to a proper Model-View-Presenter (MVP) architecture. This new, solid foundation allowed for the rapid implementation of several new features: an image rating system, selectable light/dark themes, a display cache for performance with large files, and completely redesigned settings and help dialogs. The entire transformation was completed in about a week, exclusively with Gemini's help.
</details>
 
---

## 💬 My Personal View <a name="my-personal-view"></a>

<details>
<summary>My personal view on project<a name="my-personal-view"></summary>
The genesis of Improve ImgSLI was a practical need: to create clear visual comparisons for an article. The initial design, and indeed the name, drew inspiration from imgsli.com. While the early iterations were functional, the project has since evolved significantly.

Today, I view Improve ImgSLI as a valuable public asset, much like [VideoCut](https://github.com/kanehekili/VideoCut) Kanehekili, another tool whose principles partially guided its development and which has become indispensable in my own workflow. The core value of Improve ImgSLI lies in its efficiency. Manually creating detailed image comparisons can be a laborious process, often taking several minutes. This program accomplishes the same, often superior, results in approximately 30 seconds, all through an intuitive, user-friendly interface. It's this transformation of a cumbersome task into a swift, accessible one that I believe makes Improve ImgSLI a genuinely useful tool.

It's difficult to pinpoint the exact time spent on the project, but I would estimate it to be around 100-200 hours in total, excluding the time required for package construction. The most productive period was with Cursor, though I didn't have enough time to fully adapt to its specific workflow. Furthermore, its pricing is quite steep, especially compared to Google's AI Studio for developers. The $20 plan for 400 uses per month is simply nowhere near enough for my development style.
</details>

---

## ⭐ Star History

![Star History Chart](https://api.star-history.com/svg?repos=Loganavter/Improve-ImgSLI&type=Timeline)
