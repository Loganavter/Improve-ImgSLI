# Install Improve-ImgSLI

This document provides installation methods for end users and a minimal "run from source" setup. For developer-oriented packaging/build instructions, see [CONTRIBUTING.md](../CONTRIBUTING.md).

## Quick install (recommended)

### Windows
- Download the latest installer from the Releases: https://github.com/Loganavter/Improve-ImgSLI/releases/latest
- Run the `.exe` and follow the steps.

### Linux (Flatpak)
```bash
flatpak install io.github.Loganavter.Improve-ImgSLI
flatpak run io.github.Loganavter.Improve-ImgSLI
```

### Linux (Arch AUR)
```bash
yay -S improve-imgsli
```

### macOS
Help wanted. If you can assist with a macOS build pipeline, please contribute: https://github.com/Loganavter/Improve-ImgSLI/pull/15

---

## Run from source (minimal)

This approach is for users who prefer not to install system-wide packages or want to try the app quickly from the repository.

Prerequisites:
- Python 3.10+ recommended
- Git

Steps:
```bash
git clone https://github.com/Loganavter/Improve-ImgSLI.git
cd Improve-ImgSLI
chmod +x launcher.sh
./launcher.sh run
```

The launcher:
- Creates/uses a virtual environment
- Installs dependencies
- Runs the application

Helpful commands:
```bash
./launcher.sh --help
./launcher.sh recreate       # recreate venv
./launcher.sh delete         # delete venv
./launcher.sh enable-logging # enable extended logging
```

Manual venv (optional):
```bash
python -m venv venv
source venv/bin/activate        # Linux/macOS
# .\venv\Scripts\activate      # Windows PowerShell
pip install -r requirements.txt
python -m src
```
---

**Build from Source for Windows**
If you prefer to compile the application yourself, please follow the detailed instructions. This guide ensures a clean, isolated build environment.

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
    
---

## Documentation

In-app Help (recommended):
- English: src/resources/help/en/
- Russian: src/resources/help/ru/

Entry topic (EN): src/resources/help/en/introduction.md

---

## Troubleshooting

- Blank window or crashes:
  - Ensure your GPU drivers are up-to-date.
  - Try running with logging enabled: `./launcher.sh enable-logging && ./launcher.sh run`.
- Missing fonts/icons:
  - Verify that `src/resources/` assets are available and not removed.
- Slow performance with very large images:
  - Use display cache settings within the app to match your screen resolution.
- Packaging issues (Windows/Flatpak/AUR):
  - See developer packaging notes in [CONTRIBUTING.md](../CONTRIBUTING.md).

---

## License

Improve-ImgSLI is MIT-licensed. See:
- LICENSE.txt