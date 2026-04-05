from __future__ import annotations

import io
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "build" / "Windows-template" / "Improve_ImgSLI.spec"
INNO_PATH = REPO_ROOT / "build" / "Windows-template" / "inno_setup_6.iss"
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"
SETUP_EXE = REPO_ROOT / "build" / "Windows-template" / "Output" / "Improve_ImgSLI_Setup_v8.2.0.exe"

FFMPEG_ZIP_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
FFMPEG_EXE_SUBPATH = "ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe"


def run_command(args: list[str], *, cwd: Path | None = None) -> int:
    print(f"> {' '.join(str(arg) for arg in args)}")
    completed = subprocess.run(args, cwd=cwd or REPO_ROOT)
    return int(completed.returncode)


def ensure_supported_python() -> int:
    version = sys.version_info
    if version < (3, 10):
        print(f"Unsupported Python version: {version.major}.{version.minor}.{version.micro}")
        print("Use Python 3.10+ for Windows builds.")
        return 1

    if version >= (3, 15):
        print(f"Unsupported Python version: {version.major}.{version.minor}.{version.micro}")
        print("Python 3.15+ is not validated by the pinned Windows build dependencies yet.")
        print("Use Python 3.10-3.14 for Windows builds.")
        return 1

    return 0


def ensure_python_dependencies() -> int:
    if REQUIREMENTS_PATH.exists():
        print(f"Installing application dependencies from {REQUIREMENTS_PATH}")
        if run_command([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS_PATH)]) != 0:
            print("Failed to install application dependencies.")
            return 1

    if run_command([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"]) != 0:
        print("Failed to install or update PyInstaller.")
        return 1

    if run_command([sys.executable, "-c", "import PyQt6, PyQt6.QtCore"]) != 0:
        print("PyQt6 is not importable in the selected Python environment.")
        print("Use a Python version with available PyQt6 wheels or install PyQt6 manually before building.")
        return 1

    return 0


def build_pyinstaller() -> int:
    print(f"Running PyInstaller with {SPEC_PATH}")
    args = [sys.executable, "-m", "PyInstaller", str(SPEC_PATH)]
    print(f"> {' '.join(str(arg) for arg in args)}")
    completed = subprocess.run(args, cwd=REPO_ROOT)
    return int(completed.returncode)


def dist_exe() -> Path:
    return REPO_ROOT / "dist" / "Improve_ImgSLI" / "Improve_ImgSLI.exe"


def fetch_ffmpeg() -> int:
    dist_dir = REPO_ROOT / "dist" / "Improve_ImgSLI"
    ffmpeg_dest = dist_dir / "ffmpeg.exe"

    if ffmpeg_dest.exists():
        print(f"ffmpeg.exe already present at {ffmpeg_dest}, skipping download.")
        return 0

    print(f"Downloading ffmpeg from {FFMPEG_ZIP_URL} ...")
    try:
        with urllib.request.urlopen(FFMPEG_ZIP_URL) as response:
            zip_data = response.read()
    except Exception as e:
        print(f"Failed to download ffmpeg: {e}")
        return 1

    print("Extracting ffmpeg.exe ...")
    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            with zf.open(FFMPEG_EXE_SUBPATH) as src, open(ffmpeg_dest, "wb") as dst:
                dst.write(src.read())
    except Exception as e:
        print(f"Failed to extract ffmpeg.exe: {e}")
        return 1

    print(f"ffmpeg.exe placed at {ffmpeg_dest}")
    return 0


def build_inno_setup() -> int:
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
    iscc_path = Path(program_files_x86) / "Inno Setup 6" / "ISCC.exe"
    if not iscc_path.exists():
        print("Inno Setup 6 not found. Installer skipped.")
        return 0

    build_inno = os.environ.get("BUILD_INNO_SETUP", "").strip().lower()
    if build_inno in {"1", "true", "yes", "y"}:
        return run_command([str(iscc_path), str(INNO_PATH)])
    if build_inno in {"0", "false", "no", "n"}:
        print("Installer build skipped.")
        return 0

    answer = input("Build Inno Setup installer? (y/n): ").strip().lower()
    if answer != "y":
        print("Installer build skipped.")
        return 0

    return run_command([str(iscc_path), str(INNO_PATH)])


def main() -> int:
    os.chdir(REPO_ROOT)
    print(f"Repo root: {REPO_ROOT}")
    print(f"Using Python: {sys.executable}")

    if ensure_supported_python() != 0:
        return 1

    if ensure_python_dependencies() != 0:
        return 1

    if build_pyinstaller() != 0:
        print("PyInstaller build failed.")
        return 1

    if fetch_ffmpeg() != 0:
        print("Failed to fetch ffmpeg. Continuing without it.")

    print(f"Done. Exe: {dist_exe()}")

    if build_inno_setup() != 0:
        print("Inno Setup build failed.")
        return 1

    if SETUP_EXE.exists():
        print(f"Installer: {SETUP_EXE}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
