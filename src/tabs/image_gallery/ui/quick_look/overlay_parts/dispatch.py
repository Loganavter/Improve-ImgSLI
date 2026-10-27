"""QuickLookOverlay triage dispatch — compare/multi/reject/delete/source.

Moved verbatim from ``ui/quick_look.py`` (plan-gallery-split-2026-10-17,
Part C2). Plain functions taking the overlay as their first argument; the
class keeps same-named one-line delegators (the bottom-bar button slots).

Dispatch goes through ``GalleryController`` (G3) when available, with the
storeless ``setattr`` fallbacks kept verbatim; external triage triggers
reuse ``tabs.image_gallery.use_cases.triage``.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.ui.quick_look.helpers import _set_colored_text


def _carry_point(owner, targets, pixmap=None) -> bool:
    """Carry an explicit point/target set — the ONE action surface, no scope read.

    Used by Quick Look Compare, whose scope is the card on screen: the carry
    must carry THAT card and must not narrow the gallery selection to it
    (owner requirement: "a Quick Look compare does not rewrite the selection").
    """
    try:
        from tabs.image_gallery.use_cases import gallery_actions
        from tabs.image_gallery.use_cases.action_context import (
            ORIGIN_ACTION,
            context_for_paths,
        )

        gallery_actions.carry(
            owner, context_for_paths(owner, targets, origin=ORIGIN_ACTION), pixmap=pixmap
        )
        return True
    except Exception:
        pass
    try:
        from tabs.image_gallery.use_cases import carry as _carry

        return bool(_carry._dispatch_via_image_carry(list(targets), pixmap=pixmap))
    except Exception:
        return False


def _on_compare(self) -> None:
    if self._current_item is None:
        return
    # No compareRequested.emit here: the direct path below already carries,
    # and the only subscriber (on_quick_compare) would run the carry a SECOND
    # time (double ImageCarryService.begin). on_quick_compare stays for the
    # _on_multi path, which relies on it for the carry step.
    #
    # Scope (owner report 2026-10-27): the card on screen is the scope, and the
    # gallery selection is NOT rewritten to it. The old body narrowed the
    # selection to ``{p}`` first, so comparing one previewed card silently
    # destroyed a three-card selection.
    try:
        p = Path(getattr(self._current_item, "path", ""))
        owner = self._owner
        if owner is not None and hasattr(owner, "state"):
            from tabs.image_gallery.use_cases import action_scope

            scope = action_scope.resolve_scope(
                owner, "gallery.quick_look.compare", card_path=p
            )
            targets = list(scope.targets) or [p]
            selection = action_scope.selected_paths(owner)
            pixmap = getattr(self._current_item, "thumbnail", None)
            if not selection:
                # Nothing to preserve: the viewed card becomes the compare
                # scope through the ONE writer (dispatch + mirror + grid).
                from tabs.image_gallery.use_cases import carry as _carry
                from tabs.image_gallery.use_cases import selection as _selection

                _selection.commit(owner, targets)
                _carry.carry_selected(owner)
            elif set(selection) == set(targets):
                from tabs.image_gallery.use_cases import carry as _carry

                _carry.carry_selected(owner)
            else:
                _carry_point(owner, targets, pixmap=pixmap)
    except Exception:
        pass
    # W12-A: Compare navigates away (carry flow) — dismiss the overlay.
    # Reject / Set as source stay open (triage continues); X still closes.
    try:
        self.hide()
    except Exception:
        pass


def _on_multi(self) -> None:
    if self._current_item is None:
        return
    try:
        owner = self._owner
        p = Path(getattr(self._current_item, "path", ""))
        if owner is not None and hasattr(owner, "state"):
            # Add-to-multi-compare is an ADDITIVE selection commit: it reads the
            # selection through the ONE reader and writes through the ONE writer
            # (``selection.commit`` → ``gallery_slot.set_selection``), never a
            # bare ``state.selected_paths`` merge (rule 1/2).
            try:
                from tabs.image_gallery.use_cases import selection as _selection

                _selection.commit(owner, [p], additive=True)
            except Exception:
                pass
        self.compareRequested.emit(p)
    except Exception:
        pass
    # W12-A: verified in code that _on_multi enters the compare flow
    # (compareRequested -> on_quick_compare -> carry_selected ->
    # ImageCarryService.begin), so it dismisses like Compare. Reject /
    # Set as source stay open (triage continues); X still closes.
    try:
        self.hide()
    except Exception:
        pass


def _on_reject(self) -> None:
    if self._current_item is None:
        return
    try:
        p = Path(getattr(self._current_item, "path", ""))
        owner = self._owner
        if owner is not None:
            # Quick Look's scope is the card on screen (policy row
            # ``gallery.quick_look.reject`` → card) and the application is the
            # SAME helper the card menu calls, so the two surfaces can never
            # disagree about the direction or the emitted rank snapshot.
            from tabs.image_gallery.ui.card import context_actions as _ctx_actions
            from tabs.image_gallery.use_cases import action_scope

            scope = action_scope.resolve_scope(
                owner, "gallery.quick_look.reject", card_path=p
            )
            try:
                _ctx_actions.apply_reject(owner, p, list(scope.targets))
            except Exception:
                try:
                    cur = bool(getattr(self._current_item, "rejected", False))
                    self._current_item.rejected = not cur
                except Exception:
                    pass
            try:
                w = getattr(owner, "widget", None) or owner
                if hasattr(w, "refresh_card"):
                    w.refresh_card(self._current_item)
                if hasattr(w, "set_triage"):
                    st = getattr(owner, "state", None)
                    if st is not None:
                        rejected_n = sum(1 for it in getattr(st, "items", []) if bool(getattr(it, "rejected", False)))
                        try:
                            w.stats_strip.set_rejected_count(rejected_n)
                        except Exception:
                            pass
            except Exception:
                pass
        # No rejectToggled.emit here: _on_reject already flipped the flag
        # above, and the only subscriber (on_quick_reject, wired in
        # quick_look_hooks.show_quick_look) would flip it BACK plus run a
        # second full show_for (~300ms of redundant re-populate). External
        # reject triggers (card menu, hover capsule) still reach the open
        # overlay via on_quick_reject — that path is untouched.
        self._refresh_triage_state()  # W12-A: Reject stays open — triage continues.
    except Exception:
        pass


def _refresh_triage_state(self) -> None:
    """Light refresh after a triage flag flip (reject/unreject).

    A full ``_populate()`` rebuilds the preview pipeline (TileStore
    stream + pyramid, ~1s per 5K file) — pure waste when only the
    rejected flag changed. Refresh just the flag-dependent chrome:
    reject label, brief and strip dim. Preview, metrics, artifacts
    and report stay untouched.
    """
    item = self._current_item
    if item is None:
        return
    try:
        rejected = bool(getattr(item, "rejected", False))
        if callable(_set_colored_text):
            _set_colored_text(
                self._reject_btn,
                self._t("image_gallery.quick_look.restore", "Restore")
                if rejected
                else f'✕ {self._t("image_gallery.quick_look.reject", "Reject")}',
                None,
            )
    except Exception:
        pass
    try:
        from tabs.image_gallery.ui.quick_look.helpers import populate_brief as _pb

        _pb(self, item)
    except Exception:
        pass
    try:
        self._rebuild_strip()
    except Exception:
        pass


def _on_delete(self) -> None:
    """Remove the current item from the grid (file on disk stays).

    Same scope and the same application as the card menu "Remove from view"
    (``gallery.quick_look.delete`` → card; ``context_actions.apply_remove``), so
    deleting from Quick Look cannot behave differently from the menu for the
    same card. After removal the overlay advances to the next series item; the
    last item dismisses the overlay.
    """
    if self._current_item is None:
        return
    try:
        p = Path(getattr(self._current_item, "path", ""))
        owner = self._owner
        if owner is not None:
            try:
                from tabs.image_gallery.ui.card import context_actions as _ctx_actions
                from tabs.image_gallery.use_cases import action_scope

                scope = action_scope.resolve_scope(
                    owner, "gallery.quick_look.delete", card_path=p
                )
                _ctx_actions.apply_remove(owner, p, list(scope.targets))
            except Exception:
                pass
        try:
            self._series_items = [
                m
                for m in (self._series_items or [])
                if Path(getattr(m, "path", "")) != p
            ]
        except Exception:
            self._series_items = []
        if not self._series_items:
            try:
                self.hide()
            except Exception:
                pass
            return
        try:
            self._current_idx = min(self._current_idx, len(self._series_items) - 1)
            self._current_item = self._series_items[self._current_idx]
        except Exception:
            return
        self._populate()
    except Exception:
        pass


def _on_set_source(self) -> None:
    if self._current_item is None:
        return
    try:
        p = Path(getattr(self._current_item, "path", ""))
        owner = self._owner
        # Policy row ``gallery.quick_look.set_source`` → card: the card on
        # screen, resolved by the ONE mechanism (no selection fallback, no
        # first-item guess). A refused scope means there is nothing to set.
        try:
            from tabs.image_gallery.use_cases import action_scope

            if owner is not None:
                scope = action_scope.resolve_scope(
                    owner, "gallery.quick_look.set_source", card_path=p
                )
                if scope.refused or not scope.targets:
                    return
                p = scope.targets[0]
        except Exception:
            pass
        # Already the source → the button reads "Unset": clear it and
        # return the pool to its no-source mode.
        is_src = self._source_path is not None and p == Path(self._source_path)
        if is_src:
            try:
                from tabs.image_gallery.ui.quick_look_hooks import on_quick_set_source as _set_src

                _set_src(owner, None)
            except Exception:
                pass
            self._source_path = None
            try:
                st = getattr(owner, "state", None) if owner is not None else None
                mode = getattr(st, "mode", None)
                if mode is not None:
                    self._mode = mode
            except Exception:
                pass
            self._populate()
            return
        new_mode = None
        if owner is not None:
            try:
                st = getattr(owner, "state", None)
                if st is not None:
                    # G3 dispatch-only seam: prefer controller.set_source
                    # (added by G1) when available; absent on this base,
                    # so mirror locally until the seam lands.
                    # TODO(G1): route via controller.set_source(p).
                    set_source = getattr(owner, "set_source", None)
                    if callable(set_source):
                        try:
                            set_source(p)
                        except Exception:
                            pass
                    else:
                        setattr(st, "source_path", p)
                    # P0-6: re-run mode selection so the chip flips to
                    # FIDELITY (a source hub implies fidelity mode).
                    try:
                        from tabs.image_gallery.services.mode import select_mode

                        new_mode = select_mode(
                            getattr(st, "series", None),
                            getattr(st, "items", None),
                            p,
                        )
                        st.mode = new_mode
                        # P1: the mode just changed — re-derive the metric
                        # profile on the owning controller (silent no-op on a
                        # storeless/test owner that has no producer).
                        _refresh = getattr(owner, "refresh_metric_profile", None)
                        if callable(_refresh):
                            try:
                                _refresh()
                            except Exception:
                                pass
                    except Exception:
                        new_mode = None
                w = getattr(owner, "widget", None) or owner
                if hasattr(w, "_source_path"):
                    w._source_path = p
                if hasattr(w, "stats_strip"):
                    try:
                        mode = new_mode
                        if mode is None:
                            mode = getattr(st, "mode", None) if st is not None else getattr(w, "_mode", None)
                        mode_name = getattr(mode, "value", mode) or "fidelity"
                        w.stats_strip.set_mode(str(mode_name), p)
                    except Exception:
                        pass
            except Exception:
                pass
        self._source_path = p
        if new_mode is not None:
            self._mode = new_mode
        self.setSource.emit(p)
        self._populate()  # W12-A: Set as source stays open — triage continues.
    except Exception:
        pass
