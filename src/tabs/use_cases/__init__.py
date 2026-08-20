"""Plain-function use_cases modules for `tabs.registry.TabRegistry`.

Each module here owns one orthogonal concern of `TabRegistry` (discovery,
page lifecycle, capability routing, session activation, session
persistence, appearance) as functions taking the registry instance as
their first argument, per docs/dev/CODE_PATTERNS.md's "thin owner +
use_cases/ module" pattern. `TabRegistry` itself keeps only construction,
instance state, and thin delegator methods with the same names.
"""
