## 图像属性

单个已加载图像的文件元数据与应用内上下文。对话框浮于会话之上，不改变会话中的任何内容。

### 打开对话框 {#open}

列表或槽位的上下文菜单中的 {{tr:image_compare.action.context_properties}} 项可为该图像打开 {{tr:image_properties.title}}。

:::figure{side=block width=280}
![图像属性对话框](../assets/platform/image_properties.png)
{{tr:image_properties.title}}.
:::

### 分组 {#sections}

各行按以下分组排列：

- {{tr:image_properties.section_file}} — 名称、路径、磁盘大小、格式、修改时间
- {{tr:image_properties.section_image}} — 像素尺寸、宽高比、方向、通道、颜色模式 / 配置文件（若有）
- {{tr:image_properties.section_app}} — 该图像在当前会话中的放置方式（见下）
- {{tr:image_properties.section_metadata}} — 相机 / EXIF 类字段（文件提供时）

无值的行会被省略；文件读取错误显示为 {{tr:image_properties.read_error}}。

### 应用内上下文 {#in-app}

{{tr:image_properties.section_app}} 取决于会话类型。{{tr:workspace.session_types.image_compare}} 条目携带 {{tr:image_properties.side}}（左 / 右）与 {{tr:image_properties.rating}}。{{tr:workspace.session_types.multi_compare}} 单元格携带 {{tr:image_properties.position}}。这些行描述的是会话状态，而非磁盘文件。

### 关闭 {#close}

{{tr:image_properties.close}} 关闭对话框。{{tr:image_properties.copy_all}} 将所有可见行复制到剪贴板；各行也有各自的复制操作。
