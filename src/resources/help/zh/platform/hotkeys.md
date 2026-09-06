## 快捷键

以下为默认快捷键。大多数操作快捷键可在 {{tr:menu.settings}} → {{tr:settings.keyboard}} 中重新绑定。画布上的 `WASD`、方向键、`Space` 移动与 `+`/`-` 缩放操作固定不变，无法重新绑定。

### 先搜索，再记忆 {#discover}

在记住一长串快捷键之前，先按 `Ctrl+Shift+P` 并输入名称查找。可直接在命令面板中运行该操作，需要图文说明时打开 {{tr:action.palette.learn_more}}。当焦点控件带有关联操作时，按 F1 可高亮对应的操作。

### 平台 {#platform}

- `Ctrl+,` — 设置
- `Ctrl+F1` — 帮助
- `Ctrl+N` — 会话选择器 / 新建会话
- `Ctrl+Tab` / `Ctrl+Shift+Tab` — 下一个 / 上一个工作区会话
- `Ctrl+Shift+P` — {{tr:menu.find_action}}
- `Ctrl+V` — 粘贴图像
- `Ctrl+Shift+O` / `Shift+S` / `Ctrl+Shift+S` — 打开 / 保存 / 项目另存为（`.imgsli`）
- `Ctrl+Q` — 退出

具体标签取决于所用语言包；可在设置 → 键盘 → 平台分组中重新绑定。

### {{tr:workspace.session_types.image_compare}} {#image-compare}

- `M` / `F` — 放大镜 / 冻结
- `N` / `D` — 文件名标签 / 分割线可见性
- `H` / `C` — 差异模式 / 通道模式
- `X` — 交换
- `R` / `Ctrl+E` — 录制 / 视频编辑器
- `Ctrl+S` — 快速保存
- `WASD` / `QE` / `Space` — 放大镜移动 / 间距 / 单侧预览（固定不变）
- `←↑↓→` / `+` / `-` — 平移 / 缩放（固定不变）

详情见[对比](help://comparison)、[放大镜](help://magnifier)、[视频编辑器](help://video)。

### {{tr:workspace.session_types.multi_compare}} {#multi-compare}

- `Ctrl+O` — 添加图像（如已绑定）
- `D` — 网格可见性
- `Ctrl+S` — 快速保存
- `Esc` — 退出槽位焦点
- `←↑↓→` / `+` / `-` — 平移 / 缩放（固定不变）

见 [{{tr:workspace.session_types.multi_compare}}](help://multi_compare)。

### 视频编辑器窗口 {#video-editor}

编辑器打开时：`Space` 播放/暂停，`Ctrl+Z` / `Ctrl+Y` 撤销/重做，`Delete` / `Backspace` 删除所选内容。完整编码流程见[视频编辑器](help://video)。

### 键盘导航 {#keyboard-navigation}

- `F1` — 显示聚焦控件的上下文帮助。当焦点与某个操作关联时，{{tr:menu.find_action}} 中的匹配项会高亮；否则按主题预过滤打开命令面板。
- 在 {{tr:menu.find_action}}（`Ctrl+Shift+P`）中：`↑` / `↓` 移动选择，`Enter` 运行，`Ctrl+Enter` 打开 {{tr:action.palette.learn_more}}，`Esc` 关闭面板。
- 在 {{tr:workspace.session_types.multi_compare}} 概览中，槽位焦点跟随指针：单击切换单图聚焦，`Esc` 退出。方向键用于平移画布，不会在槽位之间移动焦点。
- 在会话选择器中，方向键在卡片之间移动焦点，`Enter` 打开聚焦的卡片，等同于单击该卡片。
- 画布槽位之间没有 `Tab` 遍历：焦点跟随指针，键盘通过命令面板驱动操作。
