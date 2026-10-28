"""A finished project save must say so: tray state + system notification.

Owner report 2026-10-28: "кнопка сохранить проект не шлёт тост в аппе и в
систему". The system half was simply absent from the flow — ``project/save.py``
ended in the in-app toast and nothing else, while an image export notifies
(``image_export/save_flow.py::_on_success_notify``).

Red-before: ``ui.main_window.project.busy._notify_project_saved`` does not exist
on the previous tree — the flow had no notification call at all — so these cases
could not pass by accident.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ui.main_window.project import busy


class _Actions:
    def __init__(self) -> None:
        self.saved_paths: list[str | None] = []
        self.tray_updates = 0
        self.notifications: list[tuple[str, str, str | None]] = []

    def set_last_saved_path(self, path: str | None) -> None:
        self.saved_paths.append(path)

    def update_tray_actions_visibility(self) -> None:
        self.tray_updates += 1

    def notify_system(self, title, message, image_path=None, timeout_ms=4000) -> None:
        self.notifications.append((title, message, image_path))


def _owner(actions, *, notifications_enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        _window=SimpleNamespace(
            action_registry=actions,
            store=SimpleNamespace(
                settings=SimpleNamespace(
                    system_notifications_enabled=notifications_enabled
                )
            ),
        ),
        _tr=lambda _key, default="": default,
    )


def test_saved_project_updates_tray_and_notifies(tmp_path: Path) -> None:
    project = tmp_path / "Session.blinktable"
    project.write_bytes(b"PK\x03\x04")
    actions = _Actions()

    busy._notify_project_saved(_owner(actions), str(project))

    assert actions.saved_paths == [str(project)]
    assert actions.tray_updates == 1
    assert len(actions.notifications) == 1
    title, message, image_path = actions.notifications[0]
    assert title == "Saved" and str(project) in message
    assert image_path == str(project), "a real file is the notification icon"


def test_notifications_disabled_still_updates_tray(tmp_path: Path) -> None:
    project = tmp_path / "Session.blinktable"
    project.write_bytes(b"PK\x03\x04")
    actions = _Actions()

    busy._notify_project_saved(
        _owner(actions, notifications_enabled=False), str(project)
    )

    assert actions.saved_paths == [str(project)]
    assert actions.notifications == []


def test_missing_action_owner_does_not_raise(tmp_path: Path) -> None:
    project = tmp_path / "Session.blinktable"
    project.write_bytes(b"PK\x03\x04")
    owner = SimpleNamespace(
        _window=SimpleNamespace(action_registry=None, store=None),
        _tr=lambda _key, default="": default,
    )

    busy._notify_project_saved(owner, str(project))  # must not raise


def test_icon_is_not_offered_for_a_path_that_does_not_exist(tmp_path: Path) -> None:
    actions = _Actions()

    busy._notify_project_saved(_owner(actions), str(tmp_path / "gone.blinktable"))

    assert actions.notifications and actions.notifications[0][2] is None
