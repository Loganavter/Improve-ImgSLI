## 设置

设置按用途分组 — 常规、外观、优化、分析与键盘 — 便于一次只改一类问题。

### 打开设置 {#open-settings}

- **菜单 / 齿轮图标** — {{tr:menu.settings}} 或工具栏上的齿轮图标。
- **查找操作** — 按 `Ctrl+Shift+P`（{{tr:menu.find_action}}）并输入页面名称（{{tr:settings.general}}、{{tr:settings.appearance}}、{{tr:settings.keyboard}} 等）。
- **{{tr:action.palette.learn_more}}** — 若设置操作已关联锚点，点击后会跳转到对应位置。

### 常规 {#general}

- **{{tr:label.language}}** — en / ru / zh / pt_BR。
- **{{tr:label.theme}}** — 自动 / 浅色 / 深色。
- **{{tr:settings.system_notifications}}** — 保存后的系统桌面通知（应用内 toast 单独控制）。
- **{{tr:settings.enable_debug_logging}}** — 用于排查问题的详细日志。

### 外观 {#interface}

- **{{tr:settings.ui_mode}}** — {{tr:settings.ui_mode_beginner}} / {{tr:settings.ui_mode_advanced}} / {{tr:settings.ui_mode_expert}}。
- **{{tr:settings.ui_font}}** — 内置字体、系统字体或自定义字体。
- **限制** — 相关上限，例如显示名称的最大长度。

### {{tr:settings.optimization}} {#performance}

- **{{tr:settings.render_backend_label}}** — 取决于平台，更改后可能需要重启。
- **{{tr:settings.display_cache_resolution}}** — 限制主预览的尺寸；放大镜与导出仍使用原图（{{tr:workspace.session_types.image_compare}}）。
- **插值** — 缩放 / 放大镜 / 激光重采样的质量。
- **{{tr:settings.optimize_magnifier_movement}}** — 让镜头移动更平滑（同一页面上还可设置其插值方式）。
- **{{tr:settings.magnifier_intersection_highlight}}** — 高亮多个镜头重叠的区域。
- **{{tr:settings.magnifier_auto_color_new_instances}}** — 为新镜头分配不同的颜色。
- **{{tr:settings.recording_fps}}** — [视频编辑器](help://video)的采集帧率。

### 分析 {#analysis}

仅适用于 {{tr:workspace.session_types.image_compare}}：

- **{{tr:settings.autocrop_black_borders_on_load}}** — 加载时裁剪黑边。
- **自动 {{tr:ui.psnr}} / {{tr:ui.ssim}}** — 显示在画布下方（默认关闭）。

若该标签页提供此分组，请在 {{tr:workspace.session_types.image_compare}} 会话处于活动状态时打开此页面。

### 键盘 {#keyboard}

- **重新绑定** — 搜索操作；快捷键按平台 / {{tr:workspace.session_types.image_compare}} / {{tr:workspace.session_types.multi_compare}} 分组。
- **重置** — 可重置单个快捷键或全部快捷键。
- **固定项** — 画布上的 `WASD` 与 `Space` 保持固定——见[快捷键](help://hotkeys)。
