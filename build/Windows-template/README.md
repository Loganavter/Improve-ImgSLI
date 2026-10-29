# Windows packaging

Everything here builds the Windows bundle and the Inno Setup installer for
**BlinkTable**.

## Artifacts

| Artifact | Path |
|---|---|
| PyInstaller bundle (onedir) | `dist/BlinkTable/` |
| Executable | `dist/BlinkTable/BlinkTable.exe` |
| Installer | `build/Windows-template/Output/BlinkTable_Setup_v11.0.0.exe` |

The installer installs into `{autopf}\BlinkTable` and registers the app as
`BlinkTable` in Programs and Features.

## Where the name comes from

There is exactly one product name: `APP_NAME` in
`src/core/log_names.py` (the same constant that names the logger and the
app-data directory).

```
src/core/log_names.py  APP_NAME
        │
        ▼
build/Windows-template/product_name.py     ← derives every artifact name/path
        │                                   (spec name, dist dir, exe, setup exe)
        ├── BlinkTable.spec                (EXE/COLLECT name)
        ├── build_windows.py               (SPEC_PATH, DIST_DIR, SETUP_EXE)
        └── build/ci/validate_*.py         (bundle path, metadata checks)
```

`inno_setup_6.iss` cannot import Python (Inno's preprocessor has no Python
support), so it repeats the values as `#define` literals — including the fixed
`AppId` and `MyAppVersion "11.0.1"`. That is the *only* other place the name is
spelled, and
`build/Windows-template/check_product_name.py` is the gate that keeps it in
agreement with `APP_NAME`:

```bash
python build/Windows-template/check_product_name.py   # -> product-name consistency OK
```

It fails when `MyAppExeName != <APP_NAME>.exe`, `MyAppSetupName` does not start
with `<APP_NAME>_Setup_v`, the `[Files]` dist source is not `dist\<APP_NAME>`,
`AppId` is missing/invalid, the spec file is not `<APP_NAME>.spec`, or
`build_windows.py`/the spec spell a product name instead of deriving it. CI runs
it in the `validate` job of `.github/workflows/windows-build.yml`.

To rename the product again: change `APP_NAME`, rename the spec to
`<APP_NAME>.spec`, update the four `MyApp*` defines in `inno_setup_6.iss`, then
run the checker until it is green.

## Build

```bat
build\Windows-template\build.bat
```

or directly `python build/Windows-template/build_windows.py`. `BUILD_INNO_SETUP=0`
skips the installer; `BUILD_CONSOLE=1` (or legacy `IMGSLI_WINDOWS_CONSOLE=1`)
builds a console-subsystem exe for startup crashes. The version in the setup
file name comes from `#define MyAppVersion` — one number for the installer and
the metadata validators.

## Upgrade consequence (accepted, not automated)

The pre-rename installer derived its Inno `AppId` from the app name and
installed to `{autopf}\Improve ImgSLI`. The new installer has a **fixed**
`AppId`, so Inno treats it as a different product:

- an existing installation keeps its old `Improve ImgSLI` folder in
  `{autopf}` and its old entry in Programs and Features;
- the new build installs side by side into `{autopf}\BlinkTable` and appears as
  `BlinkTable`;
- removing the old product is left to the user.

**We deliberately do not implement automatic removal of the old product.** A
silent uninstall step is a destructive action on a user's machine (it runs the
old uninstaller, which can delete a folder the user has pointed elsewhere), and
it is not worth the risk for a cosmetic cleanup. The old folder/entry is inert:
the app's settings and logs live under the `BlinkTable` app-data directory, with
a one-time import from the legacy location.
