## Triage and Review

Work through each series, keep one winner, reject the rest, then move the rejects out of the folder.

### Keep best of series {#keep-best}

- **{{tr:image_gallery.action.keep_best}}** — marks the best of every series in one pass and rejects the rest; the stats-strip button does the same.
- **{{tr:image_gallery.action.keep_best_desc}}** — winners are re-ranked and badged per series.
- **Show all** — clears every rejected flag, undoing a keep-best pass.

### Make best and reject {#make-best-reject}

- **{{tr:image_gallery.card.make_best}}** — card action that crowns that image the winner of its series.
- **{{tr:image_gallery.card.reject}}** — card action that toggles the rejected flag on one image.
- **Remove from grid** — the reject-button behavior takes the image out of the grid without deleting any file.
- **Click a card** — opens Quick Look for a closer look before you decide.

### Clean review {#clean-review}

- **{{tr:image_gallery.action.clean_rejected}}** — {{tr:image_gallery.action.clean_rejected_desc}} (`_rejected/` under the folder). The move is move-only: files are never deleted.
- **Review overlay** — opens before the move so you can check what is about to leave the folder.
- **Undo** — clean moves can be undone, restoring files to the folder.

### Run triage again {#run-triage}

{{tr:image_gallery.action.run_triage}} reopens the current folder, which re-runs clustering from scratch. Use it after files change on disk or overrides made a mess.

### Set as source {#set-as-source}

{{tr:image_gallery.action.set_as_source}} (also {{tr:image_gallery.card.set_as_source}} on cards and in Quick Look) picks the fidelity reference that later comparisons measure against. See [Quality Metrics](help://gallery_quality#reference-source).
