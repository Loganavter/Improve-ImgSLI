## 导出

将当前画布导出为静态图像。会话录制与视频编码另属专题：[视频编辑器](help://video)。

### 保存静态图像 {#saving-an-image}

{{tr:image_compare.action.save}}（工具栏或 {{tr:menu.find_action}}）会打开导出对话框。

- **路径** — 输出目录与文件名。
- **格式** — PNG、JPEG、WEBP、BMP、TIFF 或 JXL。
- **预览** — 实时预览面板会在写入文件前显示合成结果。

:::figure{side=block width=630}
![导出对话框]({{img:workspace.image_compare.export.dialog}})
{{tr:image_compare.action.breadcrumb.toolbar}} → {{tr:image_compare.action.breadcrumb.export}}。
:::

### 分辨率与质量 {#resolution-and-quality}

- **尺寸** — 宽高输入框，附带宽高比锁定。
- **质量** — {{tr:label.quality}} 仅对有损格式显示。
- **PNG** — 压缩级别与 {{tr:export.optimize_png}}。
- **填充** — 仅当虚拟画布超出 `0..1` 时，{{tr:export.fill_background}} 才会绘制边距区域；单位画布下该选项保持关闭。

### 元数据与收藏 {#metadata-and-favorites}

- **元数据** — {{tr:export.include_metadata}} 默认开启，关闭前一直有效；注释输入框随之隐藏。{{tr:export.remember_by_default}} 会为下次导出保留注释文本。
- **收藏** — {{tr:misc.set_as_favorite}} 固定当前目录；{{tr:tooltip.use_favorite}} 召回该目录。
- **标签** — 启用 {{tr:image_compare.action.file_names}} 时，名称作为会话状态（而非文件数据）烧录到静态图像中。

### 快速保存 {#quick-save}

- **`Ctrl+S`** — {{tr:image_compare.action.quick_save}} 直接沿用上次的导出设置，不打开对话框。
- **系统托盘** — 托盘图标菜单可重新打开最近保存的文件和文件夹。

### 录制与视频 {#video-editor}

录制控制与视频/GIF 编码属于[视频编辑器](help://video)。
