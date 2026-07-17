## 对比

在整个画布上对比两张图像：可拖动分割线，支持文件名标签、通道视图与差异模式——无需打开放大镜。

### 分割线 {#split-line}

放大镜关闭时，可在两张图像上拖动分割线。

- **方向** — {{tr:image_compare.action.divider_orientation}} 可在水平 / 垂直之间切换。
- **宽度** — 在 {{tr:image_compare.action.divider_width}} 上滚动。
- **颜色** — {{tr:image_compare.action.divider_color}}。
- **可见性**（`D`）— {{tr:image_compare.action.divider_visible}} 用于显示或隐藏分割线。
- **组合控件** — {{tr:image_compare.action.divider_combined}} 集合了方向、宽度与颜色（滚轮 / 右键 / 中键）；详见控件提示。

:::figure{side=right width=280}
![分割线](ui/placeholder.png)
{{tr:image_compare.action.breadcrumb.toolbar}} → {{tr:image_compare.action.breadcrumb.divider}}（占位图）。
:::

### 滚动切换图像 {#scroll-images}

- **画布滚轮** — 切换光标所在一侧的列表（垂直分割时左侧、水平分割时上方为侧 1；另一半为侧 2）。
- **`Shift` + 滚轮** — 同时切换两个列表。
- **单图预览** — 滚轮始终切换当前可见的一侧。
- **下拉按钮滚轮** — 在不打开面板的情况下切换该侧图像；见[列表与面板](help://ui.lists_flyouts#scroll-lists)。
- **交换**（`X`）— 单击交换当前这一对图像；长按交换整个左右列表。

### 标签 {#labels-and-metrics}

- **显示名称**（`N`）— {{tr:image_compare.action.file_names}}；启用后可随导出一起烧录到图像中。
- **缩放** — 缩放不为 `100%` 时标签会隐藏，恢复适配缩放后自动重新出现。
- **文字设置** — {{tr:image_compare.action.text_settings}} 打开一个面板，可设置大小、粗细、不透明度、颜色、背景与位置。

### 指标 {#metrics}

- **{{tr:ui.psnr}} / {{tr:ui.ssim}}** — 默认关闭，可在[设置 → 分析](help://settings#analysis)中启用自动计算。
- **属性** — 从列表行的右键菜单打开[图像属性](help://image_properties)（文件元数据与应用内的侧 / 评分信息）。

### 通道模式 {#channel-modes}

{{tr:image_compare.action.channel_mode}}（`C`）在 RGB、R、G、B 与明度之间循环切换，方便在不离开画布的情况下检查单一通道。

### 差异模式 {#difference-modes}

{{tr:image_compare.action.diff_mode}}（按 `H` 循环切换）用于突出两张图像的差异之处：

:::figure{side=right width=280}
![差异模式](ui/placeholder.png)
{{tr:image_compare.action.diff_mode}}（占位图）。
:::

- **{{tr:image_compare.action.diff_highlight}}** — 在原图上高亮变化区域
- **{{tr:image_compare.action.diff_grayscale}}** — 以灰度显示强度差异
- **{{tr:image_compare.action.diff_edges}}** — 以边缘方式呈现差异
- **{{tr:image_compare.action.diff_ssim}}** — 在指标支持时显示结构相似性地图

实时画布、导出静帧与视频录制的显示效果始终一致。差异模式可与通道视图组合使用。若需局部细节检查，请使用[放大镜](help://magnifier)。
