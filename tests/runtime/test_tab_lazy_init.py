"""Lazy tab initialization (plan-lazy-tab-init): pages are built on first show.

Regression pin for the lazy mechanism in tabs/use_cases/pages.py:
after install_pages() NO page widget exists (all tabs pending), and the
first activate() creates + assembles exactly once. This is what keeps
image_compare's 30+ widgets out of the startup path.
"""

from types import SimpleNamespace

from PySide6.QtWidgets import QStackedWidget, QWidget

from tabs.registry import TabRegistry


def _fake_tab(built):
    def create_page(stack, context):
        built["created"] += 1
        return QWidget()

    def assemble_host_page(ui):
        built["assembled"] += 1

    def finalize_host_page(ui):
        built["finalized"] += 1

    return SimpleNamespace(
        session_type="fake",
        create_page=create_page,
        assemble_host_page=assemble_host_page,
        finalize_host_page=finalize_host_page,
    )


def _registry_with_fake():
    registry = TabRegistry()
    built = {"created": 0, "assembled": 0, "finalized": 0}
    registry._tabs["fake"] = _fake_tab(built)
    return registry, built


def test_install_pages_creates_nothing(qtbot):
    registry, built = _registry_with_fake()
    stack = QStackedWidget()
    qtbot.addWidget(stack)
    registry.install_pages(stack, SimpleNamespace())
    assert built == {"created": 0, "assembled": 0, "finalized": 0}
    assert "fake" in registry._pending_pages
    assert "fake" not in registry._pages


def test_first_activate_builds_once(qtbot):
    registry, built = _registry_with_fake()
    stack = QStackedWidget()
    qtbot.addWidget(stack)
    registry.install_pages(stack, SimpleNamespace())
    # Production order: host assembly runs at startup while the page is
    # still pending — it must skip uncreated pages, not build them.
    registry.assemble_host_pages(SimpleNamespace())
    assert built == {"created": 0, "assembled": 0, "finalized": 0}
    from tabs.use_cases import session_lifecycle

    session_lifecycle.activate(registry, "fake")
    assert built["created"] == 1
    assert built["assembled"] == 1
    assert registry.get_page("fake") is not None
    session_lifecycle.activate(registry, "fake")
    assert built["created"] == 1, "second show must not rebuild the page"
