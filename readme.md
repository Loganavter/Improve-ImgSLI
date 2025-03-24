# Improved ImgSLI

## Overview
Improved ImgSLI is an open-source, non-proprietary software designed for intuitive image interactions. It is completely free of charge and allows for easy distribution without the need for a license.

## Features
- Intuitive image interactions using the mouse cursor
- Image splitting along horizontal and vertical axes
- Full-resolution image saving
- Magnifying glass feature with adjustable magnification area size
- Customizable magnifying glass mirror sizes
- Independent movement of magnifying glasses using the WASD keys
- Adjustable distance between magnifying glasses using the Q and E keys
- Ability to combine magnifying glasses for comparison
- Multilingual support (English, Russian, Chinese) with flag-based language selection
- File name display on saved images with customizable font size and length limits
- Drag-and-drop support for loading images directly into the application
- Editable image names with real-time length validation
- Swap images with a single button click for quick comparison adjustments
- Persistent settings for window size, language, and preferences across sessions

---

<div style="display: flex; justify-content: space-between;">
    <img src="1.png" alt="Изображение 1" style="width: 45%;">
    <img src="2.png" alt="Изображение 2" style="width: 45%;">
</div>

## Installation
To install Improved ImgSLI, follow these steps:
```bash
git clone https://github.com/Loganavter/Improve-ImgSLI.git
cd Improve-ImgSLI
pip install -r requirements.txt
python Improve_ImgSLI.py
```

## Arch Linux 
```bash
yay -S improve-imgsli
```

---

<details>
<summary>Spoiler</summary>
Originally, Improve ImgSLI was fully crafted by ChatGPT in September 2024 to simplify creating comparison images for my work, offering basic image comparison functionality. In October, I discovered Claude and used it to enhance the tool with a magnifier feature and drag-and-drop support.

By November, with Claude’s help, I refined the magnifier, adding options to freeze the detection area and merge magnifiers. However, the growing codebase—coupled with Claude’s 8k token context limit—made full regeneration impossible, forcing me to manually edit sections. I turned to Gemini, which assisted in integrating changes, though not all generated code was successful. Some features were postponed, and others were intentionally disabled to avoid bugs.

In early December, I experimented with adaptive magnifier positioning tied to window resizing, but the results were unsatisfactory, and I abandoned the effort. Then, in January 2025, a user request to enable window resizing prompted me to explore DeepSeek—a breakthrough AI with Chain-of-Thought reasoning at the time. DeepSeek helped implement this feature, while Gemini seamlessly incorporated it and other updates into the existing code.

In late February 2025, I resumed enhancing Improve ImgSLI. With Claude Sonnet 3.7, I added dynamic image swapping via a button, a language dictionary, and further magnifier improvements, along with a help tooltip in the top-right corner. Soon after, I gained access to Grok 3—first on X, then via its website after a quick Google search. Grok 3 proved invaluable: its DeepThink model efficiently resolved persistent bugs, outperforming DeepSeek, while its generous query limits and smart standard model kept development flowing smoothly. It optimized rendering updates, introduced file name display and editing, and fixed fullscreen mode issues.

Occasionally, I leaned on the new Claude Sonnet when Grok hit prediction snags—both AIs complemented each other, though Sonnet’s 16k token context eventually fell short too. Finally, with Gemini’s assistance, I improved code readability to wrap up this round of updates.

In general, if do not take into account the price of my personal time, which is about 2 weeks in total, then this project cost me about $ 30. I got the AUR maintainer for free, so we don't take it into account either :)
</details>

<details>
<summary>Spoiler</summary>
This code was developed using ChatGPT and Claude AI over the course of 2 days for a cost of $10.
</details>
