"""Visible chrome-sync branch must move the bottom edit row with the flag.

Regression: clicking toolbar `btn_file_names` ("Текст") flipped
`render_config.include_file_names_in_saved` in the store, but
`handle_store_domain`'s *visible* branch only scheduled the `file_names`
batch (labels/edits) and never called `toggle_edit_layout_visibility` —
only the background/deferred branch did. The button toggled, the store
flipped, the panel never appeared.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_compare.use_cases.chrome_sync import ImageCompareChromeSync


def _sync(flag: bool):
    toggled = []
    batches = []
    widget = SimpleNamespace(
        toggle_edit_layout_visibility=lambda v: toggled.append(bool(v)),
        window=lambda: SimpleNamespace(
            ui=SimpleNamespace(workspace_stack=None)
        ),
        isVisible=lambda: True,
    )
    store = SimpleNamespace(
        viewport=SimpleNamespace(
            render_config=SimpleNamespace(
                include_file_names_in_saved=flag
            ),
            session_data=SimpleNamespace(
                image_state=SimpleNamespace(image1=None, image2=None)
            ),
        ),
        state_changed=SimpleNamespace(connect=lambda cb: None),
    )
    wp = SimpleNamespace(
        ui_batcher=SimpleNamespace(
            schedule_batch_update=lambda batch: batches.append(list(batch))
        ),
    )
    # NB: QObject.__init__ rejects a SimpleNamespace parent — construct
    # parentless, then attach the fake widget (prod always passes a QWidget).
    sync = ImageCompareChromeSync(
        None, store, resolve_window_presenter=lambda: wp
    )
    sync.widget = widget
    return sync, wp, toggled, batches


def test_visible_branch_shows_row_when_flag_true():
    sync, wp, toggled, batches = _sync(True)
    sync.handle_store_domain(wp, "viewport")
    assert toggled == [True]
    assert batches and "file_names" in batches[0]


def test_visible_branch_hides_row_when_flag_false():
    sync, wp, toggled, batches = _sync(False)
    sync.handle_store_domain(wp, "viewport")
    assert toggled == [False]
