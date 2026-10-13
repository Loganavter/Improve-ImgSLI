"""Help hub titles/descriptions must be translated in every supported locale.

Dogma: ``docs/dev/HELP_SYSTEM.md`` — hubs carry i18n keys
(``title_key``/``description_key``) resolved through the label layer
(``plugins.help.labels``). The toolkit i18n pack merges the English tree as
a base, so a key missing from a non-English locale is silently served the
English string; the label layer's ``FALLBACK_BADGE`` only marks the
raw-key/static-title case. This test therefore rejects both signals: a hub
label in ru/zh/pt_BR must neither carry the fallback badge nor equal the
English label.

Falsification: pre-fix, ``workspace.image_gallery`` returned the English
``"Image Gallery"`` / ``"Browse, triage, and review image folders"`` in
ru/zh/pt_BR (``image_gallery.help.hub.*`` existed only in the en pack), so
this test failed for that hub in all three locales.
"""

from __future__ import annotations

from pathlib import Path

import pytest

NON_EN_LOCALES = ("ru", "zh", "pt_BR")

#: Hubs that must expose an i18n key pair (non-vacuity guard).
_EXPECTED_KEYED_HUBS = (
    "root",
    "workspace",
    "ui",
    "platform",
    "workspace.image_compare",
    "workspace.multi_compare",
    "workspace.image_gallery",
)


def _register_all_i18n_roots() -> None:
    """Register every ``src/**/resources/i18n`` root (host + tabs + plugins)."""
    from resources.translations import add_i18n_root

    repo = Path(__file__).resolve().parents[2]
    roots = sorted((repo / "src").rglob("resources/i18n"))
    assert roots, "no i18n roots discovered under src/"
    for root in roots:
        add_i18n_root(root)


@pytest.fixture(scope="module")
def help_tree():
    from plugins.help.tree import clear_help_contributions, get_help_tree
    from tabs.registry import TabRegistry

    _register_all_i18n_roots()
    clear_help_contributions()
    registry = TabRegistry()
    registry.discover()
    registry.contribute_all_help()
    return get_help_tree()


def _hub_nodes(tree):
    return [n for n in tree.nodes.values() if n.kind == "hub"]


def test_keyed_hubs_are_present(help_tree):
    """Non-vacuity guard: the hubs under test exist and carry both keys."""
    keyed = {
        n.node_id
        for n in _hub_nodes(help_tree)
        if n.title_key and n.description_key
    }
    missing = [h for h in _EXPECTED_KEYED_HUBS if h not in keyed]
    assert not missing, f"hub(s) missing an i18n key pair: {missing}"


@pytest.mark.parametrize("language", NON_EN_LOCALES)
def test_hub_labels_are_not_english_fallbacks(help_tree, language):
    from plugins.help.labels import (
        FALLBACK_BADGE,
        node_description,
        node_title,
    )

    problems: list[str] = []
    for node in _hub_nodes(help_tree):
        for field, getter in (
            ("title", node_title),
            ("description", node_description),
        ):
            en_value = getter(node, "en")
            if not en_value:
                # Nothing to fall back to — an unset English label is not a leak.
                continue
            value = getter(node, language)
            if FALLBACK_BADGE in value:
                problems.append(
                    f"{node.node_id} [{language}] {field}: fallback badge -> {value!r}"
                )
            elif value == en_value:
                problems.append(
                    f"{node.node_id} [{language}] {field}: English fallback -> {value!r}"
                )
    assert not problems, "\n".join(problems)
