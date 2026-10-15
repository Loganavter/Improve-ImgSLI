"""Learned quality backend is mandatory — explicit availability, fail-closed.

The gallery ranker requires the learned trio (LPIPS + DISTS, reference; BRISQUE,
no-reference) via ``torch`` + ``piq``. This pins the *explicit availability*
contract introduced with the trio becoming a hard requirement:

- a ready backend reports ``backend_status() == "ready"`` and measures the trio;
- a missing / error backend reports ``"missing"`` / ``"error"`` with a reason and
  ``require_backend()`` fails closed — there is no silent empty-result path for
  the ranking consumer;
- importing ``quality_models`` never imports torch/piq (torch + PySide6 OpenMP
  segfault guard — the backend loads lazily inside the worker path);
- BRISQUE keeps its **content** gate (applicability, not availability).

The backend is injected through the single loader seam
``quality_models._import_backend`` (with a tiny fake ``torch``), so these tests
run whether or not the real torch/piq are installed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PIL")
np = pytest.importorskip("numpy")

from tabs.image_gallery.services import quality_models as qm  # noqa: E402


# --- fake backend (loader-seam injection; real torch/piq not required) -------


class _Scalar:
    def __init__(self, value: float) -> None:
        self._value = float(value)

    def item(self) -> float:
        return self._value


class _Shape:
    """Minimal tensor stub: supports .permute / .unsqueeze / scalar multiply."""

    def __init__(self, value: float = 1.0) -> None:
        self._value = float(value)

    def permute(self, *_axes):
        return self

    def unsqueeze(self, *_dims):
        return self

    def __mul__(self, factor):
        return _Shape(self._value * float(factor))


class _NoGrad:
    def __enter__(self):
        return None

    def __exit__(self, *_exc):
        return False


class _FakeTorch:
    @staticmethod
    def from_numpy(_arr):
        return _Shape()

    @staticmethod
    def no_grad():
        return _NoGrad()


class _FakeModel:
    def __init__(self, value: float) -> None:
        self._value = float(value)

    def __call__(self, *_args, **_kwargs):
        return _Scalar(self._value)


def _fake_brisque(_tensor, *, data_range):
    del data_range
    return _Scalar(_FakePiq.BRISQUE_VALUE)


class _FakePiq:
    """Stand-in for ``piq`` exposing the trio exactly like the real package."""

    LPIPS_VALUE = 0.25
    DISTS_VALUE = 0.31
    BRISQUE_VALUE = 12.5

    def LPIPS(self):
        return _FakeModel(self.LPIPS_VALUE)

    def DISTS(self):
        return _FakeModel(self.DISTS_VALUE)

    brisque = staticmethod(_fake_brisque)


def _fake_backend():
    return _FakePiq(), _FakeTorch()


@pytest.fixture
def backend(monkeypatch):
    """Reset the lazy singleton and let a test inject its own loader seam."""
    monkeypatch.setattr(qm, "_models", None)
    monkeypatch.setattr(qm, "_torch_mod", None)
    monkeypatch.setattr(qm, "_status", None)
    monkeypatch.setattr(qm, "_reason", None)
    return monkeypatch


# --- helpers ----------------------------------------------------------------


def _img(color=(100, 100, 100), size=(32, 32)):
    from PIL import Image

    return Image.new("RGB", size, color)


def _from_array(arr):
    from PIL import Image

    return Image.fromarray(arr, "RGB")


def _flat_blocks():
    a = np.zeros((128, 128, 3), np.uint8)
    a[:, :] = (30, 60, 180)
    a[20:108, 30:98] = (220, 180, 40)
    return a


def _photographic():
    rng = np.random.default_rng(0)
    return np.clip(rng.normal(128, 40, (128, 128, 3)), 0, 255).astype(np.uint8)


# --- tests -------------------------------------------------------------------


def test_fake_backend_reports_ready_and_measures_trio(backend) -> None:
    backend.setattr(qm, "_import_backend", _fake_backend)

    assert qm.backend_status() == "ready"
    assert qm.backend_reason() is None
    assert qm.available() is True
    assert qm.require_backend()["lpips"] is not None

    pair = qm.pair_metrics(_img(), _img())
    assert pair == {"lpips": pytest.approx(0.25), "dists": pytest.approx(0.31)}  # reference half

    nr = qm.nr_metrics(_from_array(_photographic()))
    assert nr == {"brisque": pytest.approx(12.5)}  # no-reference half


def test_missing_backend_is_explicit_and_fails_closed(backend) -> None:
    def _missing():
        raise ModuleNotFoundError("No module named 'piq'")

    backend.setattr(qm, "_import_backend", _missing)

    assert qm.backend_status() == "missing"
    assert qm.backend_reason()
    assert qm.available() is False
    # The fail-closed entry point a ranker must use — no silent empty result.
    with pytest.raises(qm.QualityBackendUnavailable) as excinfo:
        qm.require_backend()
    assert "piq" in str(excinfo.value)
    # The low-level getters still degrade softly for the reporting path.
    assert qm.pair_metrics(_img(), _img()) == {}
    assert qm.nr_metrics(_img()) == {}


def test_error_backend_is_distinguished_from_missing(backend) -> None:
    def _broken():
        raise RuntimeError("libgomp: failed to load")

    backend.setattr(qm, "_import_backend", _broken)

    assert qm.backend_status() == "error"
    assert "libgomp" in (qm.backend_reason() or "")
    with pytest.raises(qm.QualityBackendUnavailable):
        qm.require_backend()


def test_brisque_content_gate_survives_a_ready_backend(backend) -> None:
    backend.setattr(qm, "_import_backend", _fake_backend)
    assert qm.backend_status() == "ready"

    illustrative = _from_array(_flat_blocks())
    assert qm.is_photographic(illustrative) is False
    # Applicability gate: skipped even though availability is "ready".
    assert qm.nr_metrics(illustrative) == {}
    # ...but the gate is content-scoped, not a blanket refusal.
    assert qm.nr_metrics(_from_array(_photographic())) == {"brisque": pytest.approx(12.5)}


def test_importing_module_does_not_import_backend() -> None:
    """The heavy backend must not be imported at module-import time.

    Runs in a clean interpreter so a previously-imported torch (in the test
    session) cannot mask the assertion; proves the module stays importable and
    pulls neither torch nor piq on import.
    """
    src_root = Path(qm.__file__).parents[3]
    code = (
        "import sys\n"
        "import tabs.image_gallery.services.quality_models as qm\n"
        "assert 'torch' not in sys.modules, 'torch imported at module load'\n"
        "assert 'piq' not in sys.modules, 'piq imported at module load'\n"
        "assert callable(qm.backend_status) and callable(qm.require_backend)\n"
        "print('ok')\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_root) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith("ok")
