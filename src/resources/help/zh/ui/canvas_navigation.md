## 画布导航

在对比画布内移动：以光标为中心缩放，用中键平移，按住 `Space` 可临时全屏预览单侧图像。

### 缩放与平移 {#zoom}

- **缩放** — `Ctrl` + 滚轮，中心在光标处。
- **平移** — 鼠标中键 + 拖动，`100%` 下可用。
- **模式** — 没有单独的导航工具；手势在实时画布上生效。

:::figure{side=block width=280}
![画布缩放与平移]({{img:ui.canvas_navigation.zoom}})
{{tr:workspace.session_types.image_compare}} → 画布。
:::

### 快速单侧预览 {#quick-side-preview}

- **侧 1** — `Space` + 鼠标左键。
- **侧 2** — `Space` + 鼠标右键。
- **释放** — 恢复正常分割视图。
- **配合合并放大镜** — `Space+Shift` 在镜头内强制显示单侧图像。

### 缩放状态下的影响 {#zoom-side-effects}

- **文件名标签** — 仅在 `100%` 缩放时显示，缩放恢复为适配大小后会自动重新出现。
- **分割线** — 缩放变化时在屏幕上保持稳定位置。
- **质量** — 预览缓存与插值在 [设置 → 优化](help://settings#performance)。
