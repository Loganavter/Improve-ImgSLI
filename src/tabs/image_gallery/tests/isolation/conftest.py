"""Per-test backend-isolation counters (plan: gallery backend isolation, W0).

The leak this suite encodes is "work that belongs to the AI backend happens
while the Algorithms backend owns the screen". Proving that offscreen needs
one honest observation point on every spend/write the two backends can make,
so ``counters`` wraps the REAL functions (or a no-op for the transport) and
reports how many times each was reached in THIS test.

Counted seams (names are the modules' actual public APIs):

* ``call_sync`` — ``services.ai_client.transport.call_sync`` AND the package
  re-export ``services.ai_client.call_sync`` (``pairwise_rank`` imports the
  latter inside ``judge``; patching only the transport would miss it). Stubbed
  to a no-op: a test must never touch the network even if the leak fires.
* ``save_analysis`` — ``services.ai_cache.save_analysis`` AND the
  ``controller.save_analysis`` re-export that ``_on_analysis_ready`` imports at
  call time (patching only the service would miss the landing seam).
* ``save_local_metrics`` — ``services.metrics_cache.save_local_metrics``.
* ``profile_put`` / ``jev_put`` — ``ProfileCache.put`` / ``JevRankCache.put``.
* ``vlm_save`` — ``services.vlm_cache.save_tie_break`` / ``save_brief``.

Every gallery disk cache resolves its directory through
``services.io.project_package.cache_kind_dir``, so this fixture redirects that
ONE function to ``tmp_path``: a test can seed and clear real cache entries
without reading, writing or DELETING the developer's cache root (the reset
under test calls ``clear_all()`` on several of those stores).

No autouse/global patching: pytest's ``monkeypatch`` + started ``mock.patch``
objects are undone at teardown, and the counters are a plain ``Counter``
readable after the call.

Decode entry points (``services.proxy._build_proxy``,
``engine.store.tiled_pixel_store.TiledPixelStore.from_path``) are deliberately
NOT counted: no test in this cell drives a decode (the transport is stubbed
before any wire copy is built), and a counter nobody asserts on would be a
claim the suite does not make.
"""

from __future__ import annotations

import contextlib
from collections import Counter
from unittest import mock

import pytest

import services.io.project_package as project_package
from tabs.image_gallery.services import (
    ai_cache,
    jev_cache,
    metrics_cache,
    profile_cache,
    vlm_cache,
)
from tabs.image_gallery.services.ai_client import transport
import tabs.image_gallery.services.ai_client as ai_client_package
import tabs.image_gallery.controller as controller


def _stub_call_sync(*_args, **_kwargs):
    """No-op transport: count the attempt, never open a socket."""
    return {}


@pytest.fixture
def counters(tmp_path, monkeypatch):
    """``Counter`` of backend-isolation spend/write seams reached by the test."""
    calls: Counter = Counter()
    stack = contextlib.ExitStack()
    # Capture the REAL writers before patching: the controller re-export wraps
    # the same implementation, and a call through it must count once, not once
    # per binding.
    real_save_analysis = ai_cache.save_analysis

    def counted(name, real, *, method: bool = False):
        if method:

            def wrapper(self, *args, **kwargs):
                calls[name] += 1
                return real(self, *args, **kwargs)

        else:

            def wrapper(*args, **kwargs):
                calls[name] += 1
                return real(*args, **kwargs)

        return wrapper

    # Cache root -> tmp_path, so the reset under test cannot clear real entries.
    def _cache_dir(kind: str):
        root = tmp_path / "cache" / str(kind)
        root.mkdir(parents=True, exist_ok=True)
        return root

    monkeypatch.setattr(project_package, "cache_kind_dir", _cache_dir)

    stack.enter_context(
        mock.patch.object(
            transport, "call_sync", counted("call_sync", _stub_call_sync)
        )
    )
    stack.enter_context(
        mock.patch.object(
            ai_client_package, "call_sync", counted("call_sync", _stub_call_sync)
        )
    )
    stack.enter_context(
        mock.patch.object(
            ai_cache,
            "save_analysis",
            counted("save_analysis", real_save_analysis),
        )
    )
    stack.enter_context(
        mock.patch.object(
            controller,
            "save_analysis",
            counted("save_analysis", real_save_analysis),
        )
    )
    stack.enter_context(
        mock.patch.object(
            metrics_cache,
            "save_local_metrics",
            counted("save_local_metrics", metrics_cache.save_local_metrics),
        )
    )
    stack.enter_context(
        mock.patch.object(
            profile_cache.ProfileCache,
            "put",
            counted("profile_put", profile_cache.ProfileCache.put, method=True),
        )
    )
    stack.enter_context(
        mock.patch.object(
            jev_cache.JevRankCache,
            "put",
            counted("jev_put", jev_cache.JevRankCache.put, method=True),
        )
    )
    stack.enter_context(
        mock.patch.object(
            vlm_cache, "save_tie_break", counted("vlm_save", vlm_cache.save_tie_break)
        )
    )
    stack.enter_context(
        mock.patch.object(
            vlm_cache, "save_brief", counted("vlm_save", vlm_cache.save_brief)
        )
    )
    try:
        yield calls
    finally:
        stack.close()


__all__ = ["counters"]
