## Magnifier

This page describes the magnifier tool: capture area, internal split, additional instances, and related controls.

### Enabling And Basic Use {#enabling-and-basic-use}
- Enable **Use Magnifier**.
- Click or drag on the image to define the capture area.
- The red circle shows the original area being sampled.

### Size And Movement {#size-and-movement}
- **Magnifier Size** changes the visible magnifier size.
- **Capture Size** changes how large the sampled source region is.
- **Move Speed** affects keyboard movement.
- `WASD` moves the magnified view or the frozen magnifier.
- `QE` adjusts spacing when the magnifier halves are separated.

### Freeze {#freeze}
- **Freeze Magnifier** locks the magnifier position on screen.
- After freezing, you can continue fine adjustments with the keyboard.

### Combined Mode And Internal Split {#combined-mode-and-internal-split}
- When the two halves become close enough, or when a difference mode is active, they combine.
- In combined mode, an internal split line appears inside the magnifier.
- Its position can be changed by dragging with the **Right Mouse Button** inside the magnifier circle.

### Guide Lines {#guide-lines}
- Guide lines visually connect the magnifier to its capture area.
- The laser button toggles them on or off.
- Scrolling over the same button changes line thickness.

### Multiple Magnifiers {#multiple-magnifiers}
- Additional magnifier instances can be created.
- Each one has its own capture area, color, and guide lines.
- **Auto-color new magnifiers** helps keep instances visually distinct.
- **Highlight magnifier intersections** shows overlap between capture areas while dragging.

### Visibility Parts {#visibility-parts}
- Hover the magnifier button to open the visibility flyout.
- It can toggle the left, center, and right parts independently.
- The center part is available only when a difference mode is active.

### Orientation And Internal Divider {#orientation-and-internal-divider}
- Right-clicking the main orientation button quickly changes magnifier split orientation.
- Scrolling over the internal divider thickness button changes thickness.
- The divider color button changes the internal divider color.

### Quality And Performance {#quality-and-performance}
- The interpolation method controls magnified image quality.
- **Optimize magnifier movement** in **Settings** enables a faster mode during motion.
- After motion stops, the main high-quality method is used again.
