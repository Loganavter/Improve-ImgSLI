## 文件与项目

将图像加载到会话列表中，从剪贴板粘贴图像，并打开或保存便携式项目文件——其中包含会话布局、对比设置以及源图像的副本。

### 加载图像 {#loading-images}

- **添加文件** — 使用两侧的添加按钮（或 {{tr:menu.find_action}}）选择一个或多个文件。
- **拖放** — 将文件拖入窗口，然后选择由哪个列表或 {{tr:workspace.session_types.multi_compare}} 槽位接收。
- **粘贴**（`Ctrl+V`）— 粘贴剪贴板中的图像；出现方向浮层时，用方向键或 `WASD` 选择侧，按 `Esc` 取消。

:::figure{side=block width=280}
![粘贴方向浮层]({{img:platform.file_project.paste_overlay}})
`Ctrl+V` — 粘贴方向浮层。
:::

### 列表 {#lists}

- **{{tr:workspace.session_types.image_compare}}** — 左右列表互相独立；列表管理面板可用于重新排序、评分、重命名、查看路径、属性与删除——见[列表与面板](help://ui.lists_flyouts)。
- **{{tr:workspace.session_types.multi_compare}}** — 使用逐槽位拖放，而非双列表——见 [{{tr:workspace.session_types.multi_compare}}](help://multi_compare)。

### 项目 {#projects}

- **打开 / 保存** — 通过文件菜单（`Ctrl+Shift+O` / `Shift+S` / `Ctrl+Shift+S`，或 {{tr:menu.find_action}}）打开或保存 `.imgsli`：**保存**写入当前文件（尚未保存时打开另存为）；**另存为**在标签已重命名时使用该名称，否则用 {{tr:menu.project_untitled}}。若标签已重命名，**保存**也会改文件名。打开项目时，当前标签使用文件名。可恢复工作区会话、对比设置（分割、差异、放大镜及相关功能）以及嵌入的图像副本。
- **便携包** — 该文件是 ZIP：会话 JSON 加上 `media/` 文件夹中的原始文件字节副本（不会重新编码像素缓冲）。
- **保存时缺少源文件** — 若列表中的路径已不存在，项目仍会保存；该图像会被跳过并给出警告。
- **应用偏好** — 主题、语言与快捷键仍保存在应用设置中，不属于项目文件。
