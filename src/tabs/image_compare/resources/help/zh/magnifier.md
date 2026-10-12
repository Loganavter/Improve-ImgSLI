## 放大镜

放大镜采样对比图像对中的某一区域，在画布上显示放大视图——呈现分割线之外的局部细节。

### 启用 {#enabling}

- **开关** — 工具栏上的 {{tr:image_compare.action.magnifier}}，或按 `M`。
- **放置** — 在图像上点击或拖动以设置捕获区域（红色圆环）。
- **圆环** — 捕获圆环的大小与颜色遵循镜头样式设置。

:::figure{side=block width=280}
![放大镜镜头]({{img:workspace.image_compare.magnifier.enabling}})
{{tr:image_compare.action.breadcrumb.toolbar}} → {{tr:image_compare.action.breadcrumb.magnifier}}。
:::

### 大小与移动 {#size-and-movement}

- **镜头大小** — {{tr:image_compare.label.magnifier_size}}。
- **捕获大小** — {{tr:image_compare.label.capture_size}}（决定采样多大范围的源图像）。
- **移动** — 镜头处于活动状态时使用 `WASD`；两半分离时用 `QE` 调整间距。
- **速度** — 放大镜面板显示时可在其中调整。

### 冻结 {#freeze}

{{tr:image_compare.action.freeze}}（`F`）将镜头固定在屏幕上；键盘微调继续有效，鼠标指针仍可自由移动。

### 分割线、辅助线与颜色 {#guides-and-colors}

- **方向** — {{tr:image_compare.action.magnifier_orientation}}。
- **内部分割线** — {{tr:image_compare.action.magnifier_divider_combined}}（滚轮 / 右键）。
- **可见性** — {{tr:image_compare.action.magnifier_divider_visible}} 与 {{tr:image_compare.action.magnifier_guides}}，以及它们的宽度。
- **颜色** — {{tr:image_compare.action.magnifier_colors}} 用于设置每个实例的轮廓颜色。

### 多个实例 {#instances}

- **添加 / 移除** — {{tr:image_compare.action.magnifier_instances}} 可同时观察多个区域。
- **自动配色** — 在设置中开启该选项后，新增的镜头实例会自动获得不同颜色。

### 合并模式 {#combined-mode}

- **合并** — 当两半均可见且间距收敛到合并阈值时，它们会合并为一个镜头。
- **内部分割** — 在镜头内用鼠标右键拖动。
- **单侧预览** — `Space+Shift` 在合并镜头内强制显示其中一侧。

:::figure{side=block width=280}
![合并放大镜]({{img:workspace.image_compare.magnifier.combined_mode}})
{{tr:image_compare.action.magnifier}} 合并模式。
:::

若需要在不使用镜头的情况下进行整幅画布对比，见[对比](help://comparison)。

### 影响放大镜的设置 {#related-settings}

放大镜相关选项见[设置](help://settings#image_compare)：

- 优化放大镜移动及其插值方式
- 镜头重叠时的高亮显示
- 新增实例的自动配色
