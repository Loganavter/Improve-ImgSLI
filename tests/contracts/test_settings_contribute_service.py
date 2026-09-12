"""Settings sections contribute via create_service / notify_all (capability dogma)."""

from __future__ import annotations

from plugins.settings.registry import SettingsRegistry, get_settings_registry
from tabs.image_compare.tab import ImageCompareTab
from tabs.multi_compare.tab import MultiCompareTab


def test_image_compare_create_service_contribute_settings():
    registry = SettingsRegistry()
    tab = ImageCompareTab()
    assert tab.create_service("contribute_settings", registry) is True
    ids = {s.section_id for s in registry.all_sections()}
    assert "image_compare.analysis" in ids
    analysis = next(s for s in registry.all_sections() if s.section_id == "image_compare.analysis")
    assert analysis.owner_tab == "image_compare"


def test_multi_compare_create_service_contribute_settings_noop():
    registry = SettingsRegistry()
    tab = MultiCompareTab()
    assert tab.create_service("contribute_settings", registry) is True
    assert registry.all_sections() == []


def test_tab_contract_has_no_contribute_settings_method():
    from tabs.contract import TabContract

    assert not hasattr(TabContract, "contribute_settings") or (
        getattr(TabContract.contribute_settings, "__isabstractmethod__", False) is False
        and "contribute_settings" not in TabContract.__dict__
    )
    # Stronger: method must not be defined on the ABC body.
    assert "contribute_settings" not in TabContract.__dict__
