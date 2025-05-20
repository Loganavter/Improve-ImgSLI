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
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/1.1/Improve_ImgSLI/screenshots/github_1.png" width="32%">
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/1.1/Improve_ImgSLI/screenshots/github_2.png" width="32%">
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/1.1/Improve_ImgSLI/screenshots/github_3.png" width="32%">
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
- Marker showing the captured area.
- Adjustable source size and magnified area.
- Smooth WASD controls.
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
1. Download the installer [here](https://github.com/Loganavter/Improve-ImgSLI/releases/download/v3.1.2/Improve_ImgSLI.exe)
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
2. **Load Images** via the "Add Img(s)" button or drag-and-drop.
3. **Compare:** move the split line with your mouse. Check "Horizontal Split" to change orientation.
4. **Magnify:** enable the magnifier and adjust zoom with sliders or keys.
5. **Export:** use the save button to export a high-res composite.

https://github.com/user-attachments/assets/f2c843c2-31eb-4fb9-8eef-2d28630f2baf

---

## 🤝 Contributing <a name="contributing"></a>

Feel free to fork, submit issues, or open PRs. Contributions are welcome!

---

## 📄 License <a name="license"></a>

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## 🧠 Development Story <a name="development-story"></a>

<details>
<summary>Development Story</summary>

Originally, Improve ImgSLI was fully crafted by ChatGPT in September 2024 to simplify creating comparison images for my work, offering basic image comparison functionality. In October, I discovered Claude and used it to enhance the tool with a magnifier feature and drag-and-drop support.

By November, with Claude’s help, I refined the magnifier, adding options to freeze the view position and merge magnifiers. However, the growing codebase—coupled with Claude’s 8k token context limit—made full regeneration impossible, forcing me to manually edit sections. I turned to Gemini, which assisted in integrating changes, though not all generated code was successful. Some features were postponed, and others were intentionally disabled to avoid bugs.

In early December, I experimented with adaptive magnifier positioning tied to window resizing, but the results were unsatisfactory, and I abandoned the effort. Then, in January 2025, a user [request](https://github.com/Loganavter/Improve-ImgSLI/issues/1) to enable window resizing prompted me to explore DeepSeek—a breakthrough AI with Chain-of-Thought reasoning at the time. DeepSeek helped implement this feature, while Gemini seamlessly incorporated it and other updates into the existing code.

In February 2025, I resumed enhancing Improve ImgSLI. With Claude Sonnet 3.7, I added dynamic image swapping via a button, a language dictionary, and further magnifier improvements, along with a help tooltip in the top-right corner. Soon after, I gained access to Grok 3—first on X, then via its website after a quick Google search. Grok 3 proved invaluable: its DeepThink model efficiently resolved persistent bugs, outperforming DeepSeek, while its generous query limits and smart standard model kept development flowing smoothly. It optimized rendering updates, introduced file name display and editing, and fixed fullscreen mode issues.

In late March 2025, I focused on improving cross-platform compatibility. Gemini and Grok, utilizing their web search functions, helped draft the necessary build and packaging scripts. While I initially hoped for community assistance with maintaining builds for different platforms, skepticism from some potential contributors about the project's AI-assisted origins meant this became a solo undertaking. Consequently, preparing each platform release was time-intensive, taking considerable effort, though this thorough process did help uncover and resolve several remaining bugs before the successful launch of the cross-platform versions. However, additional reviews and inspections delayed the publication on flathab until mid-April. But during this time, I also managed to fix a few more bugs and add a list cleanup feature.

In April 2025, I turned my attention back to eliminating some very serious bugs, continuing to rely on Gemini for assistance. Ultimately, one of the most significant changes from this period was implementing window state persistence—making the application remember its position and state before closing. Honestly, I thought I'd never finish implementing that feature; it was incredibly challenging. A settings tab was also added, providing a dedicated place for language selection, choosing the output image quality, and setting the filename length preference. Following these improvements, and for the first time in a while, the builds for Windows and Flatpak were updated to incorporate all the recent changes. My plan is to put the project on hold for an extended period once I implement one final planned feature and confirm that the Flatpak maintenance process is working correctly. Subsequently, I will update the Windows and AUR builds accordingly.

In general, if do not take into account the price of my personal time, which is about 4 weeks in total, then this project cost me about $ 30. I got the AUR maintainer for free, so we don't take it into account either :)
</details>

---

## 💬 My Personal View <a name="my-personal-view"></a>

<details>
<summary>My personal view on project<a name="my-personal-view"></summary>
Initially, I was forced to create this program for illustrations in my article. I relied entirely on the design of the website - imgsli.com , hence the name. However, something like badsli. But over time, everything has improved, and now I can be proud of this most useful public asset, just like VideoCut Kahive, on whose principles I also partially relied, and in general it is my very valuable tool that saves a lot of time. That is, I could do the same job as this program manually, but it is much more convenient when it does not take 2-5 minutes, inconvenient frame selection, knowledge of ffmpeg and other things for cropping without transcoding. But this program does exactly the same thing, but in 30 seconds and with a user-friendly interface.
</details>

---

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Loganavter/Improve-ImgSLI&type=Timeline)](https://star-history.com/#Loganavter/Improve-ImgSLI&Timeline)
