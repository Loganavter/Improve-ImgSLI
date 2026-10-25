"""Find Action stubs for Image Gallery — Stage 2 triage.

Action ids (for registry, palette):
  - gallery.keep-best-of-series  — Keep best of each series (bulk reject rest)
  - gallery.clean-rejected       — Open S3 clean review overlay
  - gallery.run-triage           — (Re)run triage pass
  - gallery.set-as-source        — Set selected as source (fidelity mode)
  - gallery.reset-metrics        — Drop the measured-metrics caches + re-run
  - gallery.continue-judge       — Resume the AI judge run a call ceiling stopped

These are stubs for the host ``ActionRegistry``; wiring is via
``create_service("contribute_actions", registry)`` in ``tab.py``.
Full descriptors (label_key, run, target) are built there; this module
just documents the ids and provides optional helper to register bare entries
so the palette can list them even when no gallery tab is active.

No setStyleSheet — this module has no UI.
"""

from __future__ import annotations

# Find Action ids — must stay stable (tests / i18n keys reference them).
GALLERY_KEEP_BEST = "gallery.keep-best-of-series"
GALLERY_CLEAN_REJECTED = "gallery.clean-rejected"
GALLERY_RUN_TRIAGE = "gallery.run-triage"
GALLERY_SET_AS_SOURCE = "gallery.set-as-source"
GALLERY_RESET_METRICS = "gallery.reset-metrics"
#: The run-level continue affordance (board 2026-10-24): a call ceiling parks
#: the cards it refused, and this row resumes them. Not a scope action — the
#: parked list IS the scope (``use_cases/judge_budget.py``).
GALLERY_CONTINUE_JUDGE = "gallery.continue-judge"

ALL_GALLERY_ACTION_IDS: tuple[str, ...] = (
    GALLERY_KEEP_BEST,
    GALLERY_CLEAN_REJECTED,
    GALLERY_RUN_TRIAGE,
    GALLERY_SET_AS_SOURCE,
    GALLERY_RESET_METRICS,
    GALLERY_CONTINUE_JUDGE,
)


def register_gallery_action_stubs(registry) -> None:  # type: ignore[no-untyped-def]
    """Register minimal stubs so the palette lists the ids.

    Real run/target wiring is done by the active tab's contribute_actions;
    stubs ensure the ids are discoverable (e.g. in empty-state search) even
    when handlers are not yet bound.
    """
    try:
        from core.actions.types import ActionDescriptor
    except Exception:
        return

    # Label keys are placeholders — i18n will resolve at palette render time.
    label_map = {
        GALLERY_KEEP_BEST: "image_gallery.action.keep_best",
        GALLERY_CLEAN_REJECTED: "image_gallery.action.clean_rejected",
        GALLERY_RUN_TRIAGE: "image_gallery.action.run_triage",
        GALLERY_SET_AS_SOURCE: "image_gallery.action.set_as_source",
        GALLERY_RESET_METRICS: "image_gallery.card.reset_metrics_cache",
        GALLERY_CONTINUE_JUDGE: "image_gallery.action.continue_judge",
    }
    # Stable help paths: triage actions land on the triage page,
    # the fidelity entry lands on quality.
    help_map = {
        GALLERY_KEEP_BEST: "workspace.image_gallery.triage",
        GALLERY_CLEAN_REJECTED: "workspace.image_gallery.triage",
        GALLERY_RUN_TRIAGE: "workspace.image_gallery.triage",
        GALLERY_SET_AS_SOURCE: "workspace.image_gallery.quality",
        GALLERY_RESET_METRICS: "workspace.image_gallery.triage",
        GALLERY_CONTINUE_JUDGE: "workspace.image_gallery.triage",
    }
    for action_id in ALL_GALLERY_ACTION_IDS:
        try:
            # Skip if already registered.
            existing = None
            try:
                existing = registry.get(action_id)  # type: ignore[attr-defined]
            except Exception:
                pass
            if existing is not None:
                continue
            registry.register(
                ActionDescriptor(
                    action_id=action_id,
                    label_key=label_map.get(action_id, action_id),
                    description_key=None,
                    breadcrumb=("image_gallery.action.breadcrumb.triage", "Image Gallery"),
                    owner_tab="image_gallery",
                    topic="triage",
                    shortcut=None,
                    help_page=help_map.get(action_id),
                    run=lambda _aid=action_id: None,  # stub — no-op until active tab overwrites
                    target=None,
                )
            )
        except Exception:
            continue
