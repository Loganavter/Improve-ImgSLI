## 工作区标签与会话选择器

在标签栏中管理会话，并通过会话选择器主页打开新的对比类型。

### 会话选择器 {#session-picker}

- **打开** — {{tr:action.workspace.open_session_picker}}（或使用新增标签页控件）。
- **选择** — 点击 {{tr:workspace.session_types.image_compare}} 或 {{tr:workspace.session_types.multi_compare}} 卡片。
- **最近使用** — 最近的 ``.imgsli`` 项目（网格或列表，可按最近打开或名称排序）。单击重新打开。卡片显示项目内 ``preview.png`` 的画布预览（旧包中的 ``preview.jpg`` 仍可用；否则使用会话类型图标）。将项目文件拖到面板上可固定到列表而不打开。右键可从列表移除或在文件夹中显示。

:::figure{side=block width=420}
![会话选择器]({{img:platform.workspace.session_picker}})
{{tr:action.workspace.open_session_picker}} — {{tr:workspace.session_types.image_compare}} / {{tr:workspace.session_types.multi_compare}}。
:::

### 不通过选择器打开会话 {#new-session-actions}

在 {{tr:menu.find_action}}（`Ctrl+Shift+P`）中可以找到：

- {{tr:action.workspace.new_image_compare}}
- {{tr:action.workspace.new_multi_compare}}

想以可视化方式选择时，使用 {{tr:action.workspace.open_session_picker}} 返回主页。

### 标签栏 {#tab-strip}

- **切换** — 点击某个标签页。
- **关闭** — 移除该会话；若这是最后一个标签页，会打开会话选择器而不是退出程序。
- **右键菜单** — 重命名、关闭，或关闭其他标签页。

### 重命名标签页 {#rename}

使用标签页右键菜单中的重命名操作，输入名称并确认。在你设置自定义名称之前，自动生成的标题会随语言变化。

### 后续主题 {#next-topics}

快速上手：[入门](help://introduction)。会话工具：[对比](help://comparison) 或 [{{tr:workspace.session_types.multi_compare}}](help://multi_compare)。
