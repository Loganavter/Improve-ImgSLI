## 视频编辑器

录制一个实时的 {{tr:workspace.session_types.image_compare}} 会话，裁剪时间轴，再编码为视频或 GIF。静态图像请见[导出](help://export)。

### 录制会话 {#recording}

- **开始 / 暂停 / 停止** — {{tr:image_compare.action.record}}（`R`）、{{tr:image_compare.action.pause_recording}}，之后可用同一组控件停止录制。
- **记录内容** — 记录的是随时间变化的画布操作（缩放/平移、分割线、放大镜、加载的图像及相关设置）所构成的控制轨道与采样点，而非原始屏幕录像。
- **采集帧率** — 见 [设置 → {{tr:settings.optimization}}](help://settings#performance)（{{tr:settings.recording_fps}}）。

### 打开编辑器 {#open-editor}

停止录制后，打开 {{tr:image_compare.action.video_editor}}（`Ctrl+E`）即可拖动查看帧、编辑范围并导出。在 {{tr:menu.find_action}} 中搜索编辑器相关控件也会打开此帮助主题。

### 时间轴编辑 {#timeline}

- **拖动定位** — 拖动时间指示器。
- **选取范围** — 用选区手柄标记一段范围；{{tr:button.trim_to_selection}} 只保留该选区。
- **删除** — `Delete` / `Backspace` 删除选中的范围。
- **播放** — `Space`；撤销 / 重做 — `Ctrl+Z` / `Ctrl+Y`。

:::figure{side=right width=280}
![视频时间轴](ui/placeholder.png)
{{tr:image_compare.action.video_editor}} — 时间轴（占位图）。
:::

### 轨道与记录内容 {#tracks}

工具轨道（分割线、放大镜、视口等）显示了被记录控件随时间的变化情况。在采样点之间，编辑器会对数值进行插值，使播放效果与实时会话保持一致。

### 预览质量 {#preview-quality}

{{tr:video.preview_quality}} 只会降低编辑器内预览的画质以提升响应速度，最终编码质量不受影响。

- **{{tr:video.preview_quality_full}}** — 预览最清晰，对设备负载最大。
- **{{tr:video.preview_quality_balanced}}** — 适合大多数会话的默认折中方案。
- **{{tr:video.preview_quality_performance}}** — 拖动时感觉卡顿时可选用的更轻量预览。
- **{{tr:video.preview_quality_draft}}** — 预览速度最快，细节最少。

### 导出视频或 GIF {#export-encode}

- **画面** — 分辨率（可按需锁定宽高比）、帧率（不能高于录制帧率）、适配或裁剪；边缘留白时可选填充颜色。
- **编码器** — 在标准标签页中选择容器格式与编码器；硬件编码器仅在系统支持时显示。
- **质量** — CRF/CQ 或比特率及相关预设。
- **路径** — 输出文件；收藏目录按钮可复用上次使用的文件夹。
- **进度** — 可随时停止；日志会显示编码器的输出信息。

:::figure{side=right width=280}
![视频导出面板](ui/placeholder.png)
{{tr:image_compare.action.video_editor}} — 导出（占位图）。
:::

### {{tr:video.manual_cli}} {#manual-cli}

当标准标签页无法满足需求时，{{tr:video.manual_cli}} 标签页允许直接传入原始 FFmpeg 输出参数。除非你清楚需要哪些参数，否则请优先使用标准标签页。

### 后续主题 {#next-topics}

静态图像见[导出](help://export)。录制过程中差异模式与放大镜的表现与实时画布一致——见[对比](help://comparison)与[放大镜](help://magnifier)。
