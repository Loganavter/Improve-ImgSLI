## Video Editor

The Video Editor records a live Image Compare session as control tracks, then trims the timeline and encodes the result to video or GIF. Stills stay on [Export](help://workspace.export).

### Record a session {#recording}

- **Start / pause / stop** — **Record Video** (`R`) starts and stops the recording; **Pause Recording** pauses and resumes it.
- **What is stored** — canvas actions over time (zoom and pan, divider, magnifier, loaded images, related settings) are stored as control tracks with recording points, not as a raw screen grab.
- **Capture rate** — the recording frame rate is set by **Recording FPS** under **Image Compare** in [Settings](help://platform.settings#image_compare).

### Open the editor {#open-editor}

After the recording stops, **Video Editor** (`Ctrl+E`) opens a window where you scrub frames, edit the range, and export. Editor actions in **Find Action** open this topic.

### Timeline editing {#timeline}

- **Scrub** — drag the time cursor to move through the recording.
- **Range** — `Shift`+drag marks a span; the edge handles and the middle of the selection move independently; **Trim to Selection** removes the marked span and joins the rest.
- **Delete** — `Delete` / `Backspace` remove the selected range.
- **Play** — `Space` starts and pauses playback; `Ctrl+Z` / `Ctrl+Y` undo and redo edits.

:::figure{side=block width=100%}
![Video timeline](../assets/video_timeline.jpg)
Video Editor — timeline.
:::

### Tracks and what was captured {#tracks}

The editor shows each recorded tool as its own track (the splitter, the magnifier, the viewport, and similar), so you can see when each control changed during the session. Between recording points the editor interpolates the values, so playback matches the live session. For the magnifier, the **Capture Position** track records where the capture ring sits on the image, and the **Offset** track records how far the lens is shifted from the capture. To change the result, trim or delete ranges on the [timeline](help://workspace.image_compare.video#timeline) and use undo or redo.

### Preview quality {#preview-quality}

**Preview Quality** lowers only the in-editor preview, to keep the editor responsive; it does not change the quality of the final file.

- **Full (1.0x)** — the sharpest preview, but the heaviest on the machine; the default.
- **Balanced (0.75x)** — a lighter trade-off that suits most sessions.
- **Performance (0.5x)** — use when scrubbing feels slow.
- **Draft (0.25x)** — the fastest preview, with the least detail.

### Export video or GIF {#export-encode}

- **Frame** — sets the output resolution (lock the aspect ratio if needed), the frame rate (which cannot exceed the recording FPS), and whether the image is fitted or cropped, with an optional fill color for empty edges.
- **Codec** — chooses the container and codec on the standard tab; hardware encoders appear only when the system exposes them.
- **Quality** — sets the CRF/CQ value or the bitrate, with related presets.
- **Path** — sets the output file; the favorite-directory buttons reuse the last preferred folder.
- **Progress** — shows encoding progress; you can stop it, and the log reports encoder messages.

:::figure{side=block width=100%}
![Video export panel](../assets/video_export.jpg)
Video Editor — export.
:::

### Manual CLI {#manual-cli}

**Manual CLI** passes raw FFmpeg output arguments when the standard tab is not enough. It bypasses the editor's validation of the options, so an incorrect argument fails the encode instead of being caught in the interface.

### Next topics {#next-topics}

Still images: [Export](help://workspace.export). Diff and magnifier during recording match the live canvas — [Comparison](help://workspace.image_compare.comparison) and [Magnifier](help://workspace.image_compare.magnifier).
