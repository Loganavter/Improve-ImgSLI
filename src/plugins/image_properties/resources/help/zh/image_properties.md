## 图像属性

无需离开当前会话，即可查看已加载图像的文件元数据与应用内上下文信息。

### 打开对话框 {#open}

在 {{tr:workspace.session_types.image_compare}} 列表中的某一行，或 {{tr:workspace.session_types.multi_compare}} 的某个槽位上右键单击，选择 {{tr:image_properties.title}}。该对话框为只读，仅 {{tr:image_properties.copy_all}} 可用，用于将所有可见行复制到剪贴板。

:::figure{side=block width=280}
![图像属性对话框]({{img:platform.image_properties.open}})
{{tr:image_properties.title}}。
:::

### 分组 {#sections}

各行按以下分组显示：

- {{tr:image_properties.section_file}} — 名称、路径、磁盘占用大小、格式、修改时间
- {{tr:image_properties.section_image}} — 像素尺寸、宽高比、方向、通道，以及可用时的颜色模式 / 配置文件
- {{tr:image_properties.section_app}} — 该图像在当前会话中的放置方式（见下文）
- {{tr:image_properties.section_metadata}} — 文件提供时的相机 / EXIF 相关字段

缺失的值留空；文件读取失败时显示为 {{tr:image_properties.read_error}}。

### 应用内上下文 {#in-app}

{{tr:image_properties.section_app}} 的内容取决于会话类型。{{tr:workspace.session_types.image_compare}} 会话可能显示 {{tr:image_properties.side}}（左 / 右）与 {{tr:image_properties.rating}}；{{tr:workspace.session_types.multi_compare}} 可能显示该单元格的 {{tr:image_properties.position}} 或 {{tr:image_properties.slot}}。这些行描述的是会话状态，而非磁盘上的文件本身。

### 关闭 {#close}

{{tr:image_properties.close}} 用于关闭对话框。关闭操作不会改变列表、评分或画布内容。
