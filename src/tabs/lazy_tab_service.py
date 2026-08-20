"""Lazy resolution of tab-owned services via `TabRegistry`."""

from __future__ import annotations

from typing import Any

_LAZY_UNSET = object()


class LazyTabService:
    """Lazily resolve a tab-owned service via `TabRegistry`.

    The service is not created until first access — tab-specific services
    (toolbar, export, image_canvas, settings color pickers) are only needed
    once their owning tab is active, not at startup. ``None`` is never
    cached so re-probe happens when the tab's page is materialized. See
    docs/dev/investigations/lazy-legacy-shell-plan.md.

    ``probe_method`` selects which registry entry point resolves the
    service: ``"create_startup_service"`` (the default) for services routed
    through ``TabContract.create_service``, or
    ``"create_main_window_feature"`` for the sibling legacy-shell-feature
    entry point (``TabContract.create_main_window_feature``) — see
    "Legacy shell: routing by capability" in `tabs/use_cases/capability_routing.py`.

    ``on_resolved``, if given, is called exactly once with the resolved
    service the first time resolution succeeds — for one-time wiring
    (e.g. connecting event-handler signals) that used to happen eagerly
    right after construction and must not be repeated on every later
    attribute access, and cannot be expressed as a lazy attribute access
    itself because nothing else re-triggers it.
    """

    def __init__(
        self,
        service_id: str,
        *args: Any,
        probe_method: str = "create_startup_service",
        on_resolved=None,
        **kwargs: Any,
    ):
        self._service_id = service_id
        self._probe_method = probe_method
        self._on_resolved = on_resolved
        self._args = args
        self._kwargs = kwargs
        self._resolved: Any = _LAZY_UNSET
        self._tried: bool = False

    def _resolve(self):
        if self._resolved is not _LAZY_UNSET:
            return self._resolved
        from tabs.registry import TabRegistry

        registry = TabRegistry()
        registry.discover()
        probe = getattr(registry, self._probe_method)
        service = probe(self._service_id, *self._args, **self._kwargs)
        if service is not None:
            self._resolved = service
            self._tried = True
            if self._on_resolved is not None:
                callback, self._on_resolved = self._on_resolved, None
                callback(service)
        return self._resolved if self._tried else None

    def __getattr__(self, name: str):
        resolved = self._resolve()
        if resolved is None:
            raise AttributeError(
                f"Tab service '{self._service_id}' not available yet "
                f"(tab page not materialized)"
            )
        return getattr(resolved, name)
