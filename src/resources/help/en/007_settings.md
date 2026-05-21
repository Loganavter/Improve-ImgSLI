## Settings

This page groups settings by purpose instead of repeating the full interface as a flat list.

### Interface {#interface}
- **Language** changes the application language.
- **Theme** switches between light, dark, and automatic appearance.
- **UI Font** selects the built-in, system, or custom installed font.
- **Max Name Length (UI)** limits label length in the interface.
- **UI Mode** changes not only complexity, but also how the toolbar is meant to be used.

### UI Modes {#ui-modes}
- **Beginner**:
  - the simplest mode;
  - keeps the interface more mouse-oriented;
  - fits first-time use and quick basic comparisons.
- **Advanced**:
  - exposes more controls directly on screen;
  - fits users who want to change parameters more often without extra steps.
- **Expert**:
  - makes the interface more minimal;
  - leans more heavily on keyboard control, including `WASD` and `QE`;
  - frees as much screen space as possible for the image.

### When To Switch Modes {#when-to-switch-modes}
- If the interface feels overloaded, try **Beginner** or **Expert** depending on your workflow.
- If you want more controls visible at once, switch to **Advanced**.
- If you prefer keyboard-heavy work and want maximum canvas space, use **Expert**.

### Preview And Quality {#preview-and-quality}
- **Display Cache Resolution** limits the main preview resolution for better performance.
- The magnifier and final export still use original quality.
- The main interpolation method affects static image quality.
- The separate movement interpolation method is used only for interactive scenarios when optimization is enabled.

### Magnifier And Interactive Motion {#magnifier-and-interactive-motion}
- **Optimize magnifier movement** enables a faster mode during motion.
- **Highlight magnifier intersections** shows overlap between capture areas.
- **Auto-color new magnifiers** helps distinguish multiple instances automatically.

### Analysis And Metrics {#analysis-and-metrics}
- **Auto-calculate PSNR / SSIM** enables automatic metrics under the comparison area.
- It is disabled by default to keep the preview lighter.

### Loading And Workflow {#loading-and-workflow}
- **Auto-crop black borders on load** removes black bars at image edges when loading files.

### System And Debugging {#system-and-debugging}
- **System notifications** control notifications after save.
- **Enable debug logging** adds detailed logs for troubleshooting.

### What Is Configured Elsewhere {#configured-elsewhere}
- Video editor **Preview Quality** is changed inside the **[video editor](help://export#video-editor-preview-quality)** itself.
- Export-specific output options are chosen in the **[Export](help://export#saving-an-image)** dialog.
