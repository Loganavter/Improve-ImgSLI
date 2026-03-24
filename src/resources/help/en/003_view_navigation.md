## Canvas Navigation

This page describes how to work with the main canvas view itself: zooming, panning, and temporary overlay behavior while navigating.

### Zooming
- Hold `Ctrl` and use the mouse wheel over the canvas to zoom in or out.
- Zooming is cursor-centered, so you can quickly focus on a specific detail.
- Filename labels on the canvas are shown only at **100% zoom**. At any other zoom level they are temporarily hidden and return automatically when zoom goes back to **100%**.

### Panning
- When zoom is above `100%`, hold the **middle mouse button** and drag to pan the view.
- Panning happens inside the same window; there is no separate navigation mode.

### Split Line While Zoomed
- The comparison divider keeps its visual screen position even while zooming.
- This lets you zoom into an area first and continue working with the splitter without sudden jumps.

### Single-Image Preview
- Quick preview with `Space + Left Mouse Button / Right Mouse Button` is still the fastest way to inspect only one side.
- Some overlays and labels may simplify or hide temporarily while zoomed for performance reasons.

### What Is Controlled by Settings
- In **Settings** you can tune:
  - display cache resolution for the preview;
  - the main interpolation method;
  - a separate interpolation method for movement;
  - magnifier movement optimization;
  - automatic PSNR / SSIM calculation.
- If preview behavior feels too heavy or too soft, these are the first options to check.
