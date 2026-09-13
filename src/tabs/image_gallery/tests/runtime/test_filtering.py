from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.models import AiAnalysisResult, AnalysisStatus, GalleryItem
from tabs.image_gallery.services.filtering import filter_items


def _item(name: str, *, status=AnalysisStatus.NOT_ANALYZED, description="", tags=()):
    item = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1, analysis_status=status)
    if status == AnalysisStatus.DONE:
        item.analysis = AiAnalysisResult(
            description=description, tags=tuple(tags), model="m", analyzed_at_iso="x"
        )
    return item


def test_empty_query_returns_all_items_regardless_of_status():
    items = [
        _item("a.png", status=AnalysisStatus.NOT_ANALYZED),
        _item("b.png", status=AnalysisStatus.DONE, description="a cat", tags=["cat"]),
    ]
    assert filter_items(items, "") == items


def test_matches_description_and_tags_case_insensitively():
    cat = _item("cat.png", status=AnalysisStatus.DONE, description="A fluffy cat", tags=["animal"])
    dog = _item("dog.png", status=AnalysisStatus.DONE, description="A happy dog", tags=["animal"])

    assert filter_items([cat, dog], "CAT") == [cat]
    assert filter_items([cat, dog], "animal") == [cat, dog]


def test_unanalyzed_items_never_match_nonempty_query():
    pending = _item("p.png", status=AnalysisStatus.PENDING)
    not_analyzed = _item("n.png", status=AnalysisStatus.NOT_ANALYZED)
    errored = _item("e.png", status=AnalysisStatus.ERROR)

    assert filter_items([pending, not_analyzed, errored], "cat") == []