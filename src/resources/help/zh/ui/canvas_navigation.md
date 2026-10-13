## 画布导航

在对比画布内移动：以光标为中心缩放，用中键平移，按住 `Space` 可临时全屏预览单侧图像。

### 缩放与平移 {#zoom}

- **缩放** — `Ctrl` + 滚轮。
- **平移** — 鼠标中键 + 拖动。
- **导航工具** — 无独立工具；手势直接在实时画布上生效。

:::figure{side=block width=280}
![画布缩放与平移]({{img:ui.canvas_navigation.zoom}})
{{tr:workspace.session_types.image_compare}} → 画布。
:::

### 快速单侧预览 {#quick-side-preview}

对比画布手势（见[对比](help://comparison)）：

- **左侧** — `Space` + 鼠标左键。
- **右侧** — `Space` + 鼠标右键。
- **释放** — 回到正常分割视图。
- **配合合并放大镜** — `Space+Shift` 在镜头内强制显示单侧图像（见[放大镜](help://magnifier)）。

### 缩放状态下的影响 {#zoom-side-effects}

- **文件名标签** — 仅在 `100%` 缩放时显示，缩放恢复为适配大小后会自动重新出现。
- **分割线** — 分数位置（0–1）；缩放变化时分数保持不变。
- **渲染质量** — 插值在画布浮动面板中；后端切换在[设置 → 优化](help://settings#performance)。
