## 设置

应用行为集中在一个对话框中：内置页面，加上工作区标签页贡献的分组（图像对比分析、画廊 AI 凭据）。标签页分组始终可见，不受当前会话影响。

### 打开设置 {#open-settings}

- **菜单** — {{tr:menu.settings}}（`Ctrl+,`）。
- **工具栏** — 齿轮按钮。
- **Find Action** — `Ctrl+Shift+P`（{{tr:menu.find_action}}）加页面名（{{tr:settings.general}}、{{tr:settings.appearance}}、{{tr:settings.keyboard}}……）。
- **{{tr:action.palette.learn_more}}** — 在已标记的设置操作上打开对应的锚点。

### 在设置中搜索 {#search}

侧边栏上方的搜索框：匹配结果按分组每组一行，不论命中位置多深（控件名、分组标题、任何语言）。激活某行即打开该分组，命中的选项闪烁提示。`Esc` 清空搜索并恢复完整列表。侧边栏可拖动调整宽度。

### 常规 {#general}

- **{{tr:label.language}}** — en / ru / zh / pt_BR。
- **{{tr:label.theme}}** — auto / light / dark。
- **{{tr:settings.system_notifications}}** — 系统级通知开关。
- **{{tr:settings.enable_debug_logging}}** — 排障用的详细日志。

### 外观 {#interface}

- **{{tr:settings.ui_mode}}** — {{tr:settings.ui_mode_beginner}} / {{tr:settings.ui_mode_advanced}} / {{tr:settings.ui_mode_expert}} 单选；默认为新手，首次启动的选择落在这里。
- **{{tr:settings.ui_font}}** — 内置、系统默认或自定义字体。
- **{{tr:settings.ui_scale}}** — 界面缩放滑杆（0.5–2.5）。
- **上限** — 相关上限，如最长显示名称长度。

### 性能 {#performance}

- **{{tr:settings.render_backend_label}}** — 可选后端取决于平台；切换可能需要重启。

### {{tr:workspace.session_types.image_compare}} {#image_compare}

图像对比选项，始终可用：

- **插值** — 缩放 / 放大镜 / 激光的重采样质量。
- **{{tr:settings.optimize_magnifier_movement}}** — 更平滑的镜头移动，插值方法在同一行。
- **{{tr:settings.magnifier_intersection_highlight}}** — 高亮镜头重叠处。
- **{{tr:settings.magnifier_auto_color_new_instances}}** — 新镜头使用不同颜色。
- **{{tr:image_compare.settings.recording_fps}}** — [视频编辑器](help://workspace.image_compare.video)的采集帧率。
- **{{tr:settings.autocrop_black_borders_on_load}}** — 加载时裁掉黑色边框。
- **自动 {{tr:ui.psnr}} / {{tr:ui.ssim}}** — 指标自动读数，默认关闭。

### 键盘 {#keyboard}

- **重映射** — 快捷键按所有者分组：platform / {{tr:workspace.session_types.image_compare}} / {{tr:workspace.session_types.multi_compare}}。
- **重置** — 单个或全部快捷键。
- **固定** — 画布 `WASD` 与 `Space` 保持固定 — 见[快捷键](help://platform.hotkeys)。
