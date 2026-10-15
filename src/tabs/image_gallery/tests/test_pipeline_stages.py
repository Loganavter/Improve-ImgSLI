"""S2 — pure gallery stage-readiness gate (``use_cases/pipeline_stages``).

Proves the single-flight + completed contract without Qt: a key runs once,
a second in-flight ``begin`` is refused, a different fingerprint re-runs, an
``invalidate`` reopens a scope, and a handled failure stays retryable.
"""

from __future__ import annotations

from tabs.image_gallery.use_cases import pipeline_stages as ps

SCOPE = 7


# -- (a) completed fingerprint is skipped ---------------------------------

def test_begin_true_then_false_for_same_key():
    gate = ps.StageGate()
    assert gate.begin("metrics", SCOPE, "fp-1") is True
    gate.finished("metrics", SCOPE)
    assert gate.begin("metrics", SCOPE, "fp-1") is False


# -- (b) single-flight: a second begin before finished is refused ---------

def test_second_begin_before_finished_is_single_flight():
    gate = ps.StageGate()
    assert gate.begin("metrics", SCOPE, "fp-1") is True
    assert gate.begin("metrics", SCOPE, "fp-1") is False  # same key
    assert gate.begin("metrics", SCOPE, "fp-2") is False  # same scope, in flight


# -- (c) a different fingerprint after finished runs ----------------------

def test_different_fingerprint_after_finished_runs():
    gate = ps.StageGate()
    assert gate.begin("metrics", SCOPE, "fp-1") is True
    gate.finished("metrics", SCOPE)
    assert gate.begin("metrics", SCOPE, "fp-2") is True


# -- (d) invalidate(scope) reopens the same fingerprint -------------------

def test_invalidate_scope_allows_same_fingerprint_again():
    gate = ps.StageGate()
    assert gate.begin("metrics", SCOPE, "fp-1") is True
    gate.finished("metrics", SCOPE)
    assert gate.begin("metrics", SCOPE, "fp-1") is False
    gate.invalidate(SCOPE)
    assert gate.begin("metrics", SCOPE, "fp-1") is True


def test_invalidate_is_scoped_and_drops_in_flight():
    gate = ps.StageGate()
    gate.begin("metrics", 1, "fp")
    gate.finished("metrics", 1)
    gate.begin("metrics", 2, "fp")  # left in flight
    gate.invalidate(1)
    assert gate.begin("metrics", 1, "fp") is True   # scope 1 reopened
    assert gate.begin("metrics", 2, "fp") is False  # scope 2 still in flight


# -- (e) a handled failure stays retryable --------------------------------

def test_failure_finished_allows_retry():
    gate = ps.StageGate()
    assert gate.begin("jev_rank", SCOPE, "fp-1") is True
    try:
        raise RuntimeError("worker blew up")
    except RuntimeError:
        gate.finished("jev_rank", SCOPE, ok=False)  # handled failure
    # failure did not record completion: the same fingerprint runs again
    assert gate.begin("jev_rank", SCOPE, "fp-1") is True


def test_success_finished_records_completion():
    # Contrast for (e): the default (success) path must block a re-run.
    gate = ps.StageGate()
    assert gate.begin("jev_rank", SCOPE, "fp-1") is True
    gate.finished("jev_rank", SCOPE)
    assert gate.begin("jev_rank", SCOPE, "fp-1") is False


def test_reset_clears_completed_and_in_flight():
    gate = ps.StageGate()
    gate.begin("a", 1, "x")
    gate.finished("a", 1)
    gate.begin("b", 2, "y")  # left in flight
    gate.reset()
    assert gate.begin("a", 1, "x") is True
    assert gate.begin("b", 2, "y") is True


# -- registry (data declaration) ------------------------------------------

def test_register_and_read_stage_requires():
    before = dict(ps._STAGES)
    try:
        ps.register_stage("jev_rank", requires=("metrics_ready",))
        assert ps.stage_requires("jev_rank") == ("metrics_ready",)
    finally:
        ps._STAGES.clear()
        ps._STAGES.update(before)


def test_unregistered_stage_requires_is_empty():
    assert ps.stage_requires("not-a-registered-stage") == ()


# -- module-level default gate wrappers -----------------------------------

def test_module_wrappers_use_default_gate():
    ps.reset()
    try:
        assert ps.begin("metrics", 99, "fp") is True
        ps.finished("metrics", 99)
        assert ps.begin("metrics", 99, "fp") is False
        ps.invalidate(99)
        assert ps.begin("metrics", 99, "fp") is True
    finally:
        ps.reset()
