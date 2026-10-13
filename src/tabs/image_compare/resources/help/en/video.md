## Video Editor

A live {{tr:workspace.session_types.image_compare}} session as recorded control tracks, with timeline trim and encode to video or GIF. Stills stay on [Export](help://workspace.export).

### Record a session {#recording}

- **Start / pause / stop** — {{tr:image_compare.action.record}} (`R`), {{tr:image_compare.action.pause_recording}}, then stop from the same controls.
- **What is stored** — canvas actions over time (zoom/pan, divider, magnifier, loaded images, related settings) as control tracks — not a raw screen grab.
- **Capture rate** — [Settings](help://platform.settings#image_compare) ({{tr:settings.recording_fps}}).

### Open the editor {#open-editor}

After the recording stops, {{tr:image_compare.action.video_editor}} (`Ctrl+E`) scrubs frames, edits the range, and exports. Editor controls in {{tr:menu.find_action}} open this topic.

### Timeline editing {#timeline}

- **Scrub** — drag the time cursor.
- **Range** — `Shift`+drag marks a span; edge handles and the middle of the selection move independently; {{tr:image_compare.button.trim_to_selection}} keeps only that selection.
- **Delete** — `Delete` / `Backspace` remove the selected range.
- **Play** — `Space`; undo / redo — `Ctrl+Z` / `Ctrl+Y`.

:::figure{side=block width=100%}
![Video timeline]({{img:workspace.image_compare.video.timeline}})
{{tr:image_compare.action.video_editor}} — timeline.
:::

### Tracks and what was captured {#tracks}

The editor shows each recorded tool as its own track (splitter, magnifier, viewport, and similar), so you can see when each control changed during the session. To change the result, trim or delete ranges on the [timeline](help://workspace.image_compare.video#timeline) and use undo or redo.

### Preview quality {#preview-quality}

{{tr:video.preview_quality}} only lowers the in-editor preview for responsiveness. Final encode quality is unchanged.

- **{{tr:video.preview_quality_full}}** — sharpest preview; heaviest on the machine; the default.
- **{{tr:video.preview_quality_balanced}}** — lighter trade-off for most sessions.
- **{{tr:video.preview_quality_performance}}** — lighter preview when scrubbing feels slow.
- **{{tr:video.preview_quality_draft}}** — fastest preview; least detail.

### Export video or GIF {#export-encode}

- **Frame** — resolution (lock aspect as needed), FPS (not above recording FPS), fit vs crop; optional fill color for empty edges.
- **Codec** — container and codec on the standard tab; hardware encoders appear only when the system exposes them.
- **Quality** — CRF/CQ or bitrate and related presets.
- **Path** — output file; favorite directory buttons reuse the last preferred folder.
- **Progress** — can be stopped; the log reports encoder messages.

:::figure{side=block width=100%}
![Video export panel]({{img:workspace.image_compare.video.export_encode}})
{{tr:image_compare.action.video_editor}} — export.
:::

### {{tr:video.manual_cli}} {#manual-cli}

When the standard tab is not enough, {{tr:video.manual_cli}} passes raw FFmpeg output arguments.

### Next topics {#next-topics}

Still images: [Export](help://workspace.export). Diff and magnifier during recording match the live canvas — [Comparison](help://workspace.image_compare.comparison) and [Magnifier](help://workspace.image_compare.magnifier).
