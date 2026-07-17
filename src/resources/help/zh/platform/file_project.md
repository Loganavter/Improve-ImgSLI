## 文件与项目

将图像加载到会话列表中，从剪贴板粘贴图像，并打开或保存项目文件——项目文件只记录会话布局与路径，不包含像素数据。

### 加载图像 {#loading-images}

- **添加文件** — 使用两侧的添加按钮（或 {{tr:menu.find_action}}）选择一个或多个文件。
- **拖放** — 将文件拖入窗口，然后选择由哪个列表或 {{tr:workspace.session_types.multi_compare}} 槽位接收。
- **粘贴**（`Ctrl+V`）— 粘贴剪贴板中的图像；出现方向浮层时，用方向键或 `WASD` 选择侧，按 `Esc` 取消。

:::figure{side=right width=280}
![粘贴方向浮层](ui/placeholder.png)
`Ctrl+V` — 粘贴方向浮层（占位图）。
:::

### 列表 {#lists}

- **{{tr:workspace.session_types.image_compare}}** — 左右列表互相独立；列表管理面板可用于重新排序、评分、重命名、查看路径、属性与删除——见[列表与面板](help://ui.lists_flyouts)。
- **{{tr:workspace.session_types.multi_compare}}** — 使用逐槽位拖放，而非双列表——见 [{{tr:workspace.session_types.multi_compare}}](help://multi_compare)。

### 项目 {#projects}

- **打开 / 保存** — 通过文件菜单（或 {{tr:menu.find_action}}）打开或保存 `.imgsli-project`，可恢复布局与文件路径。
- **仅为引用** — 移动或删除源文件会导致重新打开失败，需要重新链接；像素数据不会被嵌入项目文件。
