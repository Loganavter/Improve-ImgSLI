## 列表与面板

下拉按钮会在主窗口上方打开窗口内面板。在面板中完成操作后，点击外部区域或按 `Esc` 关闭。工具栏布局与同一控件上的多种手势见[按钮与控件](help://ui.buttons)；文件名标签样式见[对比](help://comparison)。

### 列表管理面板 {#list-manager}

在 {{tr:workspace.session_types.image_compare}} 会话中，每一侧都有一个列表下拉按钮。点击即可打开该侧的列表管理面板（包含行、评分、拖拽）。若列表为空，面板不会打开。再次点击同一个下拉按钮、点击外部区域，或选中某一行，均可关闭面板。当重命名或属性对话框处于打开状态时，面板不会因失去焦点而关闭。

:::figure{side=block width=320}
![列表管理面板]({{img:ui.lists_flyouts.list_manager}})
列表下拉按钮 → 列表管理面板。
:::

### 滚动 {#scroll-lists}

- **下拉按钮滚轮** — 在不打开面板的情况下，切换该侧的当前图像。
- **画布滚轮** — 切换光标所在一侧的图像；按住 `Shift` 滚动可同时切换两侧。完整规则见[对比 → 滚动切换图像](help://comparison#scroll-images)。
- **评分滚轮** — 仅更改该行的评分，不改变当前索引。

### 行操作 {#rows}

- **选择** — 点击某一行将其设为当前图像；面板关闭，画布随之更新。
- **多选** — `Ctrl`/`Cmd`+点击切换行；在面板空白处拖出选区框。拖动任一已选行会移动整组（拖影显示数量）。
- **重新排序** — 在同一列表内拖动。
- **跨列表移动** — 将某一行拖出单面板以展开双列表模式，再放到另一个列表中。
- **路径提示** — 将鼠标悬停在被截断的名称上可查看完整路径。

### 评分 {#rating}

每一行都带有一个评分标签。可使用加减按钮，或直接在标签上滚动，无需离开面板。

### 右键菜单 {#context-menu}

- **列表行** — 重命名、复制路径、查看属性或删除。
- **画布（当前帧）** — 相同菜单并额外提供复制；重命名仅在列表中可用。

属性会打开[图像属性](help://image_properties)。

### 工具栏按钮 {#quick-list-actions}

- **添加文件** — 每个下拉按钮旁的按钮；仅添加到对应一侧。
- **交换**（`X`）— 单击交换当前这一对图像；长按交换整个左右列表。
- **删除** — 单击移除该侧的当前帧；长按清空该侧的整个列表。

### 加载 {#loading}

将文件拖放到窗口中时，会询问应由哪个列表接收。`Ctrl+V` 可粘贴剪贴板中的图像，并可能显示侧选浮层——见[文件与项目](help://file_management)。

### 标签设置面板 {#toolbar-flyouts}

打开方式：{{tr:image_compare.action.text_settings}}，或右键点击 {{tr:image_compare.action.file_names}}。关闭：`Esc` 或点击外部区域。

面板可设置字号、粗细、不透明度、文字与背景颜色、是否绘制背景，以及标签位置（边缘 / 分割线）。

:::figure{side=block width=280}
![标签设置面板]({{img:ui.lists_flyouts.toolbar_flyouts}})
{{tr:image_compare.action.text_settings}}。
:::

分割线颜色与放大镜选项面板另行设置——见[对比](help://comparison)与[放大镜](help://magnifier)。

### {{tr:workspace.session_types.multi_compare}} {#multi-compare}

{{tr:workspace.session_types.multi_compare}} 会话没有双列表面板——图像直接放入网格槽位。标签文字设置仍会打开一个面板（但没有 {{tr:workspace.session_types.image_compare}} 中的位置单选项）。详情见 [{{tr:workspace.session_types.multi_compare}}](help://multi_compare)。
