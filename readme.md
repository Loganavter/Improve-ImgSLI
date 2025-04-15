<p align="center"><img src="https://raw.githubusercontent.com/Loganavter/Improve-ImgSLI/v2.3.4/media/logo-github.svg" alt="Logo" width="384">

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/Loganavter/Improve-ImgSLI?style=flat-square)](https://github.com/Loganavter/Improve-ImgSLI/releases/latest)
[![License: MIT](https://img.shields.io/github/license/Loganavter/Improve-ImgSLI?style=flat-square)](LICENSE)

**An intuitive, open-source tool for advanced image comparison and interaction.**

<div style="display: flex; justify-content: space-between;">
    <img src="https://raw.githubusercontent.com/Loganavter/Improve-ImgSLI/v3.1.0/media/10.png" alt="Side-by-side comparison with vertical split" style="width: 32%;">
    <img src="https://raw.githubusercontent.com/Loganavter/Improve-ImgSLI/v3.1.0/media/11.png" alt="Magnifying glass tool inspecting details" style="width: 32%;">
    <img src="https://raw.githubusercontent.com/Loganavter/Improve-ImgSLI/v3.1.0/media/12.png" alt="Language selection interface" style="width: 32%;">
</div>
<details>
     <summary>Full resolution save</summary>
     <img src="https://raw.githubusercontent.com/Loganavter/Improve-ImgSLI/v3.1.1/media/13.png" alt="Another feature example" style="width: 33%;">
</details>

---

## Table of Contents

*   [Overview](#overview)
*   [Key Features](#key-features)
*   [Installation](#installation)
*   [Basic Usage](#basic-usage)
*   [Contributing](#contributing)
*   [License](#license)
*   [Development Story](#development-story)
*   [My personal view on project](#my-personal-view)

---

## Overview <a name="overview"></a>

Improved ImgSLI is an open-source, non-proprietary software designed for intuitive image interactions. It's completely free, allowing easy distribution without restrictive licensing. It's built for anyone needing detailed image comparison, analysis, or manipulation, such as designers, upscale enthusiasts, photographers, or researchers.

---

## Key Features <a name="key-features"></a>

**Core Comparison & Viewing:**
*   Intuitive image splitting (horizontal/vertical) controlled by mouse.
*   Display original resolution (WxH) for each loaded image.
*   Automatic resizing of images to match the largest dimensions for consistent comparison.
*   Save the current comparison view (including split line, magnifier, capture marker, and optional file names) as a full-resolution image.

**Magnifier Tool:**
*   Powerful Magnifier for close inspection.
*   Visual marker (red circle) indicating the magnifier's capture area on the main image.
*   Adjustable magnification area size and magnifier display size.
*   Adjustable movement speed for WASD magnifier control.
*   Independent magnifier movement using WASD keys (with smooth interpolation).
*   Adjust distance between magnifiers using Q and E keys (with smooth interpolation).
*   Option to combine magnifiers for direct comparison of magnified areas.
*   Freeze the magnifier's view position.

**File & Workflow Management:**
*   Drag-and-drop support for loading one or multiple images per panel.
*   Select loaded images via dropdown menus when multiple images are loaded into a panel.
*   Swap entire image lists between panels with a single button click.
*   Clear image lists for each panel individually using Trash (🗑️) buttons.
*   Edit image names directly within the application interface.
*   Option to include file names in the saved comparison image.
*   Customizable font size and color for included file names.
*   Adjustable maximum length for displayed file names with visual warnings.

**User Experience & Interface:**
*   Multilingual support (English, Russian, Chinese, Brazilian Portuguese) with flag-based language selection.
*   Dynamic window resizing with adaptive content rendering(relative coords).
*   Persistent settings for window state, language, and various display preferences across sessions.

---

## Installation <a name="installation"></a>

**Python (from source):**
*   Requires: Python, pip, bash
```bash
git clone https://github.com/Loganavter/Improve-ImgSLI.git
cd Improve-ImgSLI
chmod +x launcher.sh
./launcher.sh
```

**Arch Linux (AUR):**
```bash
yay -S improve-imgsli
```

**Windows (Inno Setup):**
1.  Directly download it from [>>>here<<<](https://github.com/Loganavter/Improve-ImgSLI/releases/download/v3.1.2/Improve_ImgSLI.exe)
2.  Run the installer and follow the prompts.

**Flatpak (FlatHub):**
*   Requires: Flatpak
```bash
flatpak install io.github.Loganavter.Improve-ImgSLI
flatpak run io.github.Loganavter.Improve-ImgSLI
```

**MacOS:**
*   Help wanted! We are looking for assistance to create and maintain a macOS build. [See the discussion and contribute here](https://github.com/Loganavter/Improve-ImgSLI/pull/15).

---

## Basic Usage <a name="basic-usage"></a>

1.  **Launch:** Start Improved ImgSLI using the method corresponding to your installation.
2.  **Load Images:** Use the "Add Img(s)" buttons or drag and drop image files onto the left or right half of the main image display area. If you load multiple files onto one side, use the dropdown menu above it to select the active image.
3.  **Compare:** In the standard comparison mode, click and drag the mouse on the image to move the separator line. Use the "Horizontal Split" checkbox to change the split orientation.
4.  **Magnify:** Activate the Magnifier tool via its checkbox. In this mode, clicking or dragging on the image sets the central capture point. Use WASD keys to move the magnified view areas independently. Use Q/E keys to adjust the distance between the magnifier circles. You can also freeze the capture point using the corresponding checkbox (WASD will then move the frozen point).
5.  **Save:** Click the "Save Result" button in the UI to export the current comparison view as a single image file.

https://github.com/user-attachments/assets/f2c843c2-31eb-4fb9-8eef-2d28630f2baf

---

## Contributing <a name="contributing"></a>

Contributions are welcome! Feel free to:
*   Report bugs or suggest features by opening an [Issue](https://github.com/Loganavter/Improve-ImgSLI/issues).
*   Submit improvements by creating a [Pull Request](https://github.com/Loganavter/Improve-ImgSLI/pulls).

<details>
<summary>Unaccounted-for contributors (thanks a lot)</summary>
Yes, I'm not very good at github, so it's possible.

*   [johnpetersa19](https://github.com/Loganavter/Improve-ImgSLI/pull/14)
</details>
---

## License <a name="license"></a>

This project is distributed under the MIT License. See the [LICENSE](https://github.com/Loganavter/Improve-ImgSLI/blob/main/LICENSE.txt) file for more details.

---

[![Star History Chart](https://api.star-history.com/svg?repos=Loganavter/Improve-ImgSLI&type=Date)](https://star-history.com/#loganavter/Improve-ImgSLI&Date)

---

<details>
<summary>Development Story <a name="development-story"></a></summary>

Originally, Improve ImgSLI was fully crafted by ChatGPT in September 2024 to simplify creating comparison images for my work, offering basic image comparison functionality. In October, I discovered Claude and used it to enhance the tool with a magnifier feature and drag-and-drop support.

By November, with Claude’s help, I refined the magnifier, adding options to freeze the view position and merge magnifiers. However, the growing codebase—coupled with Claude’s 8k token context limit—made full regeneration impossible, forcing me to manually edit sections. I turned to Gemini, which assisted in integrating changes, though not all generated code was successful. Some features were postponed, and others were intentionally disabled to avoid bugs.

In early December, I experimented with adaptive magnifier positioning tied to window resizing, but the results were unsatisfactory, and I abandoned the effort. Then, in January 2025, a user [request](https://github.com/Loganavter/Improve-ImgSLI/issues/1) to enable window resizing prompted me to explore DeepSeek—a breakthrough AI with Chain-of-Thought reasoning at the time. DeepSeek helped implement this feature, while Gemini seamlessly incorporated it and other updates into the existing code.

In February 2025, I resumed enhancing Improve ImgSLI. With Claude Sonnet 3.7, I added dynamic image swapping via a button, a language dictionary, and further magnifier improvements, along with a help tooltip in the top-right corner. Soon after, I gained access to Grok 3—first on X, then via its website after a quick Google search. Grok 3 proved invaluable: its DeepThink model efficiently resolved persistent bugs, outperforming DeepSeek, while its generous query limits and smart standard model kept development flowing smoothly. It optimized rendering updates, introduced file name display and editing, and fixed fullscreen mode issues.

In late March 2025, I focused on improving cross-platform compatibility. Gemini and Grok, utilizing their web search functions, helped draft the necessary build and packaging scripts. While I initially hoped for community assistance with maintaining builds for different platforms, skepticism from some potential contributors about the project's AI-assisted origins meant this became a solo undertaking. Consequently, preparing each platform release was time-intensive, taking considerable effort, though this thorough process did help uncover and resolve several remaining bugs before the successful launch of the cross-platform versions. However, additional reviews and inspections delayed the publication on flathab until mid-April. But during this time, I also managed to fix a few more bugs and add a list cleanup feature.

In general, if do not take into account the price of my personal time, which is about 3.5 weeks in total, then this project cost me about $ 30. I got the AUR maintainer for free, so we don't take it into account either :)
</details>
<details>
<summary>My personal view on project<a name="my-personal-view"></summary>
Initially, I was forced to create this program for illustrations in my article. I relied entirely on the design of the website - imgsli.com , hence the name. However, something like badsli. But over time, everything has improved, and now I can be proud of this most useful public asset, just like VideoCut Kahive, on whose principles I also partially relied, and in general it is my very valuable tool that saves a lot of time. That is, I could do the same job as this program manually, but it is much more convenient when it does not take 2-5 minutes, inconvenient frame selection, knowledge of ffmpeg and other things for cropping without transcoding. But this program does exactly the same thing, but in 30 seconds and with a user-friendly interface.
</details>

