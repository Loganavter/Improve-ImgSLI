## 多图对比概览

在一个会话中使用布局网格、逐槽位拖放与聚焦模式，同时对比多张图像。

### 打开会话 {#open-session}

在会话选择器中选择 {{tr:workspace.session_types.multi_compare}}，或在 {{tr:menu.find_action}}（`Ctrl+Shift+P`）中运行 {{tr:action.workspace.new_multi_compare}}。另见[工作区标签](help://session_picker)。

### 布局与缝隙拆分 {#layouts}

- **网格** — 排列槽位；可将文件拖到某个单元格上，也可使用 {{tr:multi_compare.action.add_images}}（`Ctrl+O`）。
- **空槽位** — 保持打开状态，等待新的拖放。
- **缝隙拖放** — 将文件拖到单元格之间的缝隙上，可递归拆分并创建新的单元格。
- **权重** — 拖动网格分割线可调整相对大小。
- **切换布局** — 会尽量保留已加载的图像。

:::figure{side=block width=320}
![多图对比网格]({{img:workspace.multi_compare.overview.layouts}})
{{tr:workspace.session_types.multi_compare}} — 网格 / 缝隙拖放。
:::

### 聚焦模式 {#focus-mode}

- **进入** — 双击某个槽位可进入全画布聚焦模式。
- **退出** — 按 `Esc` 返回网格视图。
- **导航** — 缩放与平移方式与 {{tr:workspace.session_types.image_compare}} 相同；见[画布导航](help://view_navigation)。

### 网格与标签 {#grid-and-labels}

- **可见性**（`D`）— {{tr:multi_compare.action.divider_visible}}。
- **颜色 / 宽度** — {{tr:multi_compare.action.divider_color}} 与 {{tr:multi_compare.action.divider_width}}。
- **标签文字** — {{tr:multi_compare.action.text_settings}} 打开样式设置（没有 {{tr:workspace.session_types.image_compare}} 中的位置单选项）。

### 槽位右键菜单 {#context-menu}

右键单击某个槽位可查看该图像的相关操作，包括[图像属性](help://image_properties)（文件元数据与槽位位置），以及**移动**（拖拽幽灵 → 点击其他工作区标签以启动与拖放/粘贴相同的放置流程）。

### 保存与导出 {#save-and-export}

- **快速保存**（`Ctrl+S`）— {{tr:multi_compare.action.quick_save}}。
- **保存对话框** — {{tr:multi_compare.action.save}}（工具栏或 {{tr:menu.find_action}}）。
- **一致性** — 导出结果与实时网格保持一致（布局、标签、分割线样式），而不是单个 {{tr:workspace.session_types.image_compare}} 分割视图。

在 {{tr:workspace.session_types.multi_compare}} 标签页处于焦点状态时，可在 {{tr:menu.find_action}} 中搜索保存 / 导出相关操作。
