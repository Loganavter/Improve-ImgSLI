## 导出

将当前画面保存为静态图像。录制与视频编辑器另见专题：[视频编辑器](help://video)。

### 保存静态图像 {#saving-an-image}

{{tr:image_compare.action.save}}（`Ctrl+Shift+S`）会打开导出对话框。

- **路径** — 输出目录与文件名。
- **格式** — PNG、JPEG、WEBP、BMP、TIFF 或 JXL。
- **预览** — 实时预览面板会在写入文件前显示合成结果。

:::figure{side=right width=280}
![导出对话框](ui/placeholder.png)
{{tr:image_compare.action.breadcrumb.toolbar}} → {{tr:image_compare.action.breadcrumb.export}}（占位图）。
:::

### 分辨率与质量 {#resolution-and-quality}

- **尺寸** — 已知源尺寸时可设置宽高；锁定可保持宽高比。
- **质量** — 有损格式的 {{tr:label.quality}}。
- **PNG** — 压缩级别与 {{tr:export.optimize_png}}。
- **填充** — 支持透明的格式可启用 {{tr:export.fill_background}} 并选择填充颜色。

### 元数据与收藏 {#metadata-and-favorites}

- **元数据** — {{tr:export.include_metadata}}；可选注释与 {{tr:export.remember_by_default}}。
- **收藏** — 浏览过某个目录后，可使用 {{tr:misc.set_as_favorite}} / {{tr:tooltip.use_favorite}}。
- **标签** — 启用 {{tr:image_compare.action.file_names}} 时，名称会被烧录到静态图像中。

### 快速保存 {#quick-save}

- **`Ctrl+S`** — 使用上次的导出设置进行 {{tr:image_compare.action.quick_save}}。
- **`Ctrl+Shift+S`** — 始终打开对话框。
- **系统托盘** — 可在[设置 → 常规](help://settings#general)中开启对最近保存文件的快捷访问。

### 录制与视频 {#video-editor}

若需要录制会话并编码为视频或 GIF，见[视频编辑器](help://video)。静态图像与视频始终与实时画布保持视觉一致（包括差异模式）。
