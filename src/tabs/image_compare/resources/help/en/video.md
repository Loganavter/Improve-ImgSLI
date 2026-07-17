## Video Editor

Record a live {{tr:workspace.session_types.image_compare}} session, trim the timeline, then encode to video or GIF. Stills stay on [Export](help://export).

### Record a session {#recording}

- **Start / pause / stop** — {{tr:image_compare.action.record}} (`R`), {{tr:image_compare.action.pause_recording}}, then stop from the same controls.
- **What is stored** — canvas actions over time (zoom/pan, divider, magnifier, loaded images, related settings) as control tracks with sample points — not a raw screen grab.
- **Capture rate** — [Settings → Performance](help://settings#performance) ({{tr:settings.recording_fps}}).

### Open the editor {#open-editor}

After you stop, open {{tr:image_compare.action.video_editor}} (`Ctrl+E`) to scrub frames, edit the range, and export. Searching editor controls in {{tr:menu.find_action}} also opens this help topic.

### Timeline editing {#timeline}

- **Scrub** — drag the time cursor.
- **Range** — selection handles mark a span; {{tr:button.trim_to_selection}} keeps only that selection.
- **Delete** — `Delete` / `Backspace` remove the selected range.
- **Play** — `Space`; undo / redo — `Ctrl+Z` / `Ctrl+Y`.

:::figure{side=right width=280}
![Video timeline](ui/placeholder.png)
{{tr:image_compare.action.video_editor}} — timeline (placeholder).
:::

### Tracks and what was captured {#tracks}

Tool tracks (splitter, magnifier, viewport, and similar) show how recorded controls change over time. Between sample points the editor blends values so playback follows the live session.

### Preview quality {#preview-quality}

{{tr:video.preview_quality}} only lowers the in-editor preview for responsiveness. Final encode quality is unchanged.

- **{{tr:video.preview_quality_full}}** — sharpest preview; heaviest on the machine.
- **{{tr:video.preview_quality_balanced}}** — default trade-off for most sessions.
- **{{tr:video.preview_quality_performance}}** — lighter preview when scrubbing feels slow.
- **{{tr:video.preview_quality_draft}}** — fastest preview; least detail.

### Export video or GIF {#export-encode}

- **Frame** — resolution (lock aspect as needed), FPS (not above recording FPS), fit vs crop; optional fill color for empty edges.
- **Codec** — container and codec on the standard tab; hardware encoders appear only when the system exposes them.
- **Quality** — CRF/CQ or bitrate and related presets.
- **Path** — output file; favorite directory buttons reuse the last preferred folder.
- **Progress** — can be stopped; the log reports encoder messages.

:::figure{side=right width=280}
![Video export panel](ui/placeholder.png)
{{tr:image_compare.action.video_editor}} — export (placeholder).
:::

### {{tr:video.manual_cli}} {#manual-cli}

The {{tr:video.manual_cli}} tab passes raw FFmpeg output arguments when the standard tab is not enough. Prefer the standard tab unless you know the flags you need.

### Next topics {#next-topics}

Still images: [Export](help://export). Diff and magnifier during recording match the live canvas — [Comparison](help://comparison) and [Magnifier](help://magnifier).
