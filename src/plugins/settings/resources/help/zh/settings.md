## 设置

设置按任务分组 — 常规、外观、性能和键盘 — 每个提供设置的工作区标签页还有独立分组（{{tr:workspace.session_types.image_compare}}，…）。标签页分组始终可见，不受当前会话影响，因此标签页选项有固定位置。

### 打开设置 {#open-settings}

- **菜单 / 齿轮图标** — {{tr:menu.settings}} 或工具栏上的齿轮图标。
- **查找操作** — 按 `Ctrl+Shift+P`（{{tr:menu.find_action}}）并输入页面名称（{{tr:settings.general}}、{{tr:settings.appearance}}、{{tr:settings.keyboard}} 等）。
- **{{tr:action.palette.learn_more}}** — 若设置操作已关联锚点，点击后会跳转到对应位置。

### 在设置中搜索 {#search}

侧边栏上方有一个搜索框：输入任意内容后，匹配的分组会逐个列出 — 每个分组一行，无论匹配项藏得多深（控件名称、分组标题、任意语言）。点击某一行即可打开该分组：其中匹配的选项会高亮显示（若同一层级有多个匹配项，则全部高亮）。搜索支持所有界面语言，与{{tr:menu.find_action}}一致。按 `Esc` 可清空搜索并恢复完整侧边栏。侧边栏本身可以调整大小 — 拖动它与设置内容之间的分隔条即可。

### 常规 {#general}

- **{{tr:label.language}}** — en / ru / zh / pt_BR。
- **{{tr:label.theme}}** — 自动 / 浅色 / 深色。
- **{{tr:settings.system_notifications}}** — 保存后的系统桌面通知（应用内 toast 单独控制）。
- **{{tr:settings.enable_debug_logging}}** — 用于排查问题的详细日志。

### 外观 {#interface}

- **{{tr:settings.ui_mode}}** — {{tr:settings.ui_mode_beginner}} / {{tr:settings.ui_mode_advanced}} / {{tr:settings.ui_mode_expert}}。
- **{{tr:settings.ui_font}}** — 内置字体、系统字体或自定义字体。
- **{{tr:settings.ui_scale}}** — 独立于系统显示缩放的界面缩放（0.5–2.5）；即时生效 — 控件、字体、图标和间距会立即调整大小。
- **限制** — 相关上限，例如显示名称的最大长度。

### 性能 {#performance}

- **{{tr:settings.render_backend_label}}** — 取决于平台，更改后可能需要重启。

### {{tr:workspace.session_types.image_compare}} {#image_compare}

图像对比相关的选项位于独立分组，始终可用：

- **{{tr:settings.display_cache_resolution}}** — 限制主预览的尺寸；放大镜与导出仍使用原图。
- **插值** — 缩放 / 放大镜 / 激光重采样的质量。
- **{{tr:settings.optimize_magnifier_movement}}** — 让镜头移动更平滑（同一页面上还可设置其插值方式）。
- **{{tr:settings.magnifier_intersection_highlight}}** — 高亮多个镜头重叠的区域。
- **{{tr:settings.magnifier_auto_color_new_instances}}** — 为新镜头分配不同的颜色。
- **{{tr:settings.recording_fps}}** — [视频编辑器](help://video)的采集帧率。
- **{{tr:settings.autocrop_black_borders_on_load}}** — 加载时裁剪黑边。
- **自动 {{tr:ui.psnr}} / {{tr:ui.ssim}}** — 显示在画布下方（默认关闭）。

### 键盘 {#keyboard}

- **重新绑定** — 搜索操作；快捷键按平台 / {{tr:workspace.session_types.image_compare}} / {{tr:workspace.session_types.multi_compare}} 分组。
- **重置** — 可重置单个快捷键或全部快捷键。
- **固定项** — 画布上的 `WASD` 与 `Space` 保持固定——见[快捷键](help://hotkeys)。
