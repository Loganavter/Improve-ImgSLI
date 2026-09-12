"""Preview-tier picker for the IC live canvas (thin owner + use_cases).

Split from ``render_flow.py`` per ``docs/dev/CODE_PATTERNS.md`` — ``render_flow``
keeps the thin delegators (import forwarding), this module owns the picker
bodies as plain functions. ``_update_preview_tracking`` takes ``presenter``
as its first argument (CODE_PATTERNS: functions taking the owner); the
pure picker helpers keep their original signatures.
"""

from shared.rendering.display_image_picker import pick_display_image
from shared.rendering.image_identity import image_uid


def pick_display_with_preview_backing(
    *candidates, last_applied_uid=None, superseded_preview_uid=None
):
    """Display-pair picker for the live canvas (stored role).

    ``pick_display_image`` only returns a ``TiledPixelStore`` once its
    pyramid is complete, so the first-load path naturally shows the 1024px
    preview as the backing until the pyramid catches up. On-the-fly content
    changes (swap, next image, auto-crop resizing the store, a fresh
    preview arriving while the previous unified store is still installed)
    can bypass that: the store's pyramid is already complete, so the canvas
    flips straight to store tiles whose fallback-LOD baseline is the
    *previous* content -- the new preview never appears underneath.

    Rule: while the slot's preview is *fresh*, prefer the preview for the
    stored role regardless of pyramid state. The next apply cycle (unify
    result / pyramid-completion invalidation) then finds the preview no
    longer fresh, picks the store as usual, and the flip's fallback
    baseline is exactly the new preview tiles -- the backing survives every
    on-the-fly change instead of only the first load.

    Freshness is *not* "uid differs from the display pair last applied":
    ``image_uid`` is a per-object identity, so a preview and the store
    built from the same image always differ, and that test alone would
    re-degrade an already-sharp store back to the 1024px preview on every
    apply cycle (flip-flop). The caller therefore also passes
    ``superseded_preview_uid`` -- the uid of the preview that the
    currently-installed store superseded. A preview matching either the
    last-applied display or that superseded preview is the same image's
    and must never preempt its store; only a preview belonging to a
    different image (or a reload) counts as fresh.
    """
    preview = candidates[1] if len(candidates) > 1 else None
    if preview is not None:
        uid = image_uid(preview)
        if uid != last_applied_uid and uid != superseded_preview_uid:
            return preview
    return pick_display_image(*candidates)


def _display_cache_key(image1, image2):
    """Stored-role ids for the *effective* display pair.

    Must mirror ``live_presentation.display_cache_key``'s shape
    (``(uid1, uid2, size1, size2)``): ``upload_pil_images`` persists it as
    ``_stored_image_ids`` and ``_textures_are_current`` compares the next
    plan's key against it, so a preview-backed apply has to record the
    preview ids -- otherwise the pyramid-complete pick would compute store
    ids and the flip would be skipped by the scene-only path.
    """
    return (
        image_uid(image1),
        image_uid(image2),
        image1.size if image1 is not None else None,
        image2.size if image2 is not None else None,
    )


def _update_preview_tracking(presenter, picked_by_slot: dict) -> None:
    """Remember which preview uid was last shown per slot and which preview
    a store superseded -- using ``image_uid`` equality, not ``is``.

    Must be called on *any* successful pick (dual, scene-only, single-side)
    so the ``pick_display_with_preview_backing`` freshness check
    (last_applied/superseded) can gate the next store pick correctly.
    A recreated ``QImage`` from the same file has a different ``id``/``is``
    but the same ``image_uid`` -- ``is`` comparison misses it and the flip-
    flop guard never arms.
    """
    try:
        doc = presenter.store.get_session_state_slot("document")
    except Exception:
        doc = None
    try:
        img_state = presenter.store.viewport.session_data.image_state
    except Exception:
        img_state = None
    last_display = dict(getattr(presenter, "_last_display_uids", None) or {})
    applied = dict(getattr(presenter, "_last_applied_preview_uid", None) or {})
    superseded = dict(getattr(presenter, "_last_superseded_preview_uid", None) or {})
    for slot, picked in (picked_by_slot or {}).items():
        if picked is None:
            continue
        try:
            uid = image_uid(picked)
        except Exception:
            continue
        if uid is None or uid == 0:
            continue
        last_display[slot] = uid
        preview = None
        store_img = None
        try:
            if doc is not None:
                path = getattr(doc, f"image{slot}_path", None)
                # Phase 3: preview via PipelineCache, not document field
                _ctrl2 = getattr(presenter, "session_controller", None) or getattr(presenter, "controller", None)
                _pl2 = getattr(_ctrl2, "pipeline", None) if _ctrl2 is not None else None
                if _pl2 is not None and path:
                    try:
                        preview = _pl2.peek_preview(path)
                    except Exception:
                        preview = None
                else:
                    try:
                        ps = presenter.store.get_session_state_slot("pipeline")
                        if ps is not None and path:
                            import os

                            from tabs.image_compare.pipeline.cache import _preview_key

                            k = _preview_key(path, None, None)
                            preview = ps.preview.get(k)  # type: ignore[attr-defined]
                            if preview is not None and hasattr(preview, "isNull") and preview.isNull():
                                preview = None
                    except Exception:
                        preview = None
        except Exception:
            preview = None
        try:
            if img_state is not None:
                store_img = getattr(img_state, f"image{slot}", None)
        except Exception:
            store_img = None
        preview_uid = None
        store_uid = None
        try:
            preview_uid = image_uid(preview) if preview is not None else None
        except Exception:
            preview_uid = None
        try:
            store_uid = image_uid(store_img) if store_img is not None else None
        except Exception:
            store_uid = None
        # uid equality, not ``is`` -- a recreated QImage has a new identity
        # but the same stable uid.
        if preview_uid is not None and preview_uid != 0 and uid == preview_uid:
            applied[slot] = uid
        elif store_uid is not None and store_uid != 0 and uid == store_uid:
            prev_applied = applied.get(slot)
            if prev_applied is not None:
                superseded[slot] = prev_applied
    presenter._last_display_uids = last_display
    presenter._last_applied_preview_uid = applied
    presenter._last_superseded_preview_uid = superseded
