## 按钮与控件

工具栏位于对比会话画布上方，承载该会话的工具：分割线、视图模式、放大镜、录制。列表、添加/保存以及设置齿轮则在周围的窗口边栏中。

### 工具栏 {#toolbar}

- **位置** — 画布上方的一排图标控件。
- **内容** — 切换、数值微调，以及为当前会话类型打开面板或对话框的按钮。
- **疏密** — 取决于 {{tr:settings.ui_mode}}（首次启动引导或[设置 → 外观](help://settings#interface)）。

:::figure{side=block height=107}
![会话工具栏]({{img:ui.buttons.toolbar}})
画布上方的工具栏。
:::

### 界面模式 {#ui-modes}

同一套工具在不同 {{tr:settings.ui_mode}} 下布局不同。首次启动时选择一次，之后可在设置中更改。

### {{tr:settings.ui_mode_beginner}} {#mode-beginner}

更多独立按钮 — 一个控件 ≈ 一件事。适合鼠标操作，也更容易找到每项功能。

:::figure{side=block height=65}
![初级工具栏布局]({{img:ui.buttons.mode_beginner}})
{{tr:settings.ui_mode}} → {{tr:settings.ui_mode_beginner}}。
:::

### {{tr:settings.ui_mode_advanced}} {#mode-advanced}

图标更少。部分控件已把单击与滚轮组合在一起（例如方向 + 粗细）。

:::figure{side=block height=65}
![高级工具栏布局]({{img:ui.buttons.mode_advanced}})
{{tr:settings.ui_mode}} → {{tr:settings.ui_mode_advanced}}。
:::

### {{tr:settings.ui_mode_expert}} {#mode-expert}

最紧凑：同一控件可承载单击、滚轮及其他鼠标按键，把更多空间留给图像。

:::figure{side=block height=65}
![专家工具栏布局]({{img:ui.buttons.mode_expert}})
{{tr:settings.ui_mode}} → {{tr:settings.ui_mode_expert}}。
:::

### 同一控件上的多种操作 {#multi-action}

在 {{tr:settings.ui_mode_advanced}}，尤其是 {{tr:settings.ui_mode_expert}} 中，同一图标经常对应多项操作：

- **单击** — 主要操作或切换。
- **滚轮** — 微调数值（分割线粗细、放大镜大小等），无需打开对话框。
- **长按** — 部分列表按钮的强化操作（清空整列表；交换两侧列表）。
- **其他鼠标按键**（专家） — 例如在紧凑分割线控件上右键取色、中键重置。

{{tr:settings.ui_mode_beginner}} 会把这些任务拆成独立按钮，而不是叠在同一个控件上。

:::figure{side=block height=44}
![列表按钮上的长按]({{img:ui.buttons.long_press}})
列表按钮 — 单击与长按。
:::

### 产品示例 {#examples}

- **{{tr:workspace.session_types.image_compare}}** — 在更紧凑的模式下，可在同一控件上滚动调整分割线宽度或放大镜大小；列表按钮支持长按清空 / 交换。详情见[列表与面板](help://ui.lists_flyouts)。
- **{{tr:workspace.session_types.multi_compare}}** — 网格线（`D`）同样具备粗细 / 可见性相关手势。

### 按名称查找控件 {#find-action}

按 `Ctrl+Shift+P`（{{tr:menu.find_action}}），输入标签名称的一部分，然后运行该操作；若该行带有帮助主题，可打开 {{tr:action.palette.learn_more}} 或按 `Ctrl+Enter`。
