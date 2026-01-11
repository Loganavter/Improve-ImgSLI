## Magnifier Tool

### Basics
- Check **Use Magnifier** to enable it.
- **Click/drag** on the main image to set the capture point (red circle).
- **Freeze Magnifier:** Lock the magnifier position on screen. While frozen, you can still move the view with `WASD`.

### Controls
- **Magnifier Size slider:** Controls the zoom level.
- **Capture Size slider:** Adjusts the size of the area being sampled from the original image.
- **Move Speed slider:** Sets the speed for keyboard movement.
- **Keyboard `WASD`:** Moves the magnified view relative to the capture point (or moves the entire frozen magnifier).
- **Keyboard `QE`:** Adjusts the spacing between the two magnifier halves when they are separated.
- **Interpolation:** Choose a resampling method (e.g., Nearest, Bilinear, Lanczos, EWA Lanczos) to control the rendering quality of the zoomed image.
  - **EWA Lanczos:** An advanced method using supersampling to simulate EWA (Elliptical Weighted Average) Lanczos. Provides superior anti-aliasing by first upscaling the image 2×, then downscaling with Lanczos filtering. Excellent for reducing moiré and aliasing in detailed images.


### High-Precision Rendering
- The magnifier uses subpixel rendering to ensure smooth and accurate comparisons, even when the two images have different resolutions.
- This eliminates pixel jitter when moving the capture point and provides a more precise view of details.


### Combined Halves and Internal Split
- When the spacing between the two magnifier halves becomes small enough, or when a difference mode is active, the halves automatically combine into a single circle with an internal split line.
- You can adjust the internal split position by dragging with the Right Mouse Button inside the magnifier circle.

### Guide Lines ("Lasers")
- To visually connect the magnifier to its capture point on the main image, you can enable guide lines.
- Click the laser icon button on the magnifier toolbar to toggle them on or off.
- The thickness of these lines can be adjusted by scrolling the mouse wheel over the same button.

### Visibility Flyout (Left/Center/Right)
- Hover over the Magnifier button to reveal a small flyout that lets you toggle visibility of the left, center, and right parts.
- You can also open this flyout by scrolling the mouse wheel over the Magnifier button; in this case it auto-hides shortly after.
- The Center toggle is available only when a difference mode is active.

### Quick Orientation Toggle
- Right-click the main Orientation button to quickly toggle the magnifier split orientation. A small popup indicator will confirm the current orientation.

### Magnifier Divider Controls
- Divider thickness (inside the magnifier): scroll the mouse wheel over the Magnifier Divider Thickness button to adjust the thickness. A small numeric popup shows the current value.
- Divider color (inside the magnifier): click the Magnifier Divider Color button to choose a color.

### Performance Optimization
- For a smoother experience when moving the magnifier (dragging the capture point or using WASD keys), you can enable **"Optimize magnifier movement"** in the Settings.
- This uses a faster, lower-quality interpolation method during movement, while the high-quality method selected in the main UI is used as soon as the magnifier stops.
