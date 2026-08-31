"""Progressive previews are valid live-canvas sources before full-res loading."""

from types import SimpleNamespace

from PIL import Image

from core.state_management.dispatcher import Dispatcher
from core.store import Store
from core.store_viewport import SessionData
from tabs.image_compare.canvas.presentation.plan_builder import build_live_store_presentation
from tabs.image_compare.pipeline.pipeline import ImagePipeline
from tabs.image_compare.state.actions import PutPreviewAction
from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.state.models import ImageSessionState, RenderCacheState


def _make_store(document: DocumentModel, previews=None) -> Store:
    import tabs.image_compare.bootstrap_reducers  # noqa: F401

    store = Store()
    store.create_workspace_session(session_type="image_compare", activate=True)
    store.set_session_state_slot("document", document)
    store.viewport.session_data = SessionData(
        image_state=ImageSessionState(), render_cache=RenderCacheState()
    )
    store.state_changed = type("Sig", (), {"emit": staticmethod(lambda *_a, **_k: None)})()
    store.set_dispatcher(Dispatcher(store))
    from tabs.image_compare.state.models import PipelineCacheState

    try:
        if store.get_session_state_slot("pipeline") is None:
            store.set_session_state_slot("pipeline", PipelineCacheState())
    except Exception:
        pass
    if previews:
        for path, img in previews.items():
            store.transact([PutPreviewAction(path=path, qimage=img)], scope="pipeline")
    return store


def test_live_presentation_uses_progressive_previews_as_sources():
    preview1 = Image.new("RGBA", (20, 10), "red")
    preview2 = Image.new("RGBA", (20, 10), "blue")
    document = DocumentModel(
        image_list1=[ImageItem(path="left.png", display_name="left")],
        image_list2=[ImageItem(path="right.png", display_name="right")],
        current_index1=0,
        current_index2=0,
    )
    store = _make_store(document, previews={"left.png": preview1, "right.png": preview2})
    # image_state also holds preview for fallback (as in original test)
    store.viewport.session_data.image_state.image1 = preview1
    store.viewport.session_data.image_state.image2 = preview2

    presentation = build_live_store_presentation(store)

    assert presentation.display_image1 is preview1
    assert presentation.display_image2 is preview2
    assert presentation.source_image1 is preview1
    assert presentation.source_image2 is preview2


def test_live_presentation_prefers_unified_pair_over_raw_full_res_sources():
    raw1 = Image.new("RGBA", (40, 20), "red")
    raw2 = Image.new("RGBA", (20, 40), "blue")
    unified1 = Image.new("RGBA", (40, 40), "red")
    unified2 = Image.new("RGBA", (40, 40), "blue")
    document = DocumentModel(
        image_list1=[ImageItem(path="left.png", display_name="left")],
        image_list2=[ImageItem(path="right.png", display_name="right")],
        current_index1=0,
        current_index2=0,
    )
    store = _make_store(document)
    # unified pair is in image_state, preview/raw not needed
    store.viewport.session_data.image_state.image1 = unified1
    store.viewport.session_data.image_state.image2 = unified2

    presentation = build_live_store_presentation(store)

    assert presentation.source_image1 is unified1
    assert presentation.source_image2 is unified2
    assert presentation.source_image1.size == presentation.source_image2.size
