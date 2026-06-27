from __future__ import annotations

from dataclasses import replace


def reduce_magnifier_cache_state(cache_state, action):
    del action
    return replace(cache_state, feature_caches={})
