## Settings

- **Language:** Changes the UI language.
- **Theme:** Choose between Auto, Light, or Dark mode.
- **UI Font:** Select between the built-in font, your system default, or a custom installed font.
- **Max Name Length (UI):** Limits the length of filenames displayed in the UI.
- **Display Cache Resolution:** Sets a resolution limit for the main preview to improve performance with large images. The magnifier and final export always use original quality.
- **Movement Interpolation:** When "Optimize magnifier movement" is enabled, this selects a faster, lower-quality interpolation method (like Bilinear) to use *only* during interactive movement for a smoother experience. The high-quality method is still used when static.
- **Optimize magnifier movement:** Enables the use of the separate, faster interpolation method above during magnifier movement. Enabled by default.
- **Auto-calculate PSNR / SSIM:** Toggles the automatic calculation and display of PSNR and SSIM metrics below the image. Disabled by default for better performance. Note: SSIM will still be calculated and shown if the "SSIM Map" diff mode is active.
- **Enable debug logging:** Toggles detailed logging for troubleshooting.
- **System notifications:** Toggles system notifications on save.
