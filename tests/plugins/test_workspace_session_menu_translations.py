"""Workspace session menu labels follow the active application language."""

from types import SimpleNamespace

from ui.presenters.main_window.workspace import configure_workspace_actions


class _Button:
    def __init__(self):
        self.actions = []

    def set_actions(self, actions):
        self.actions = actions

    def isVisible(self):
        return True

    def isEnabled(self):
        return True

    @property
    def clicked(self):
        return SimpleNamespace(disconnect=lambda *_: None, connect=lambda *_: None)


def test_workspace_session_menu_uses_russian_labels():
    blueprints = [
        SimpleNamespace(
            session_type=session_type,
            resolved_title=lambda title=title: title,
        )
        for session_type, title in (
            ("image_compare", "Image Compare"),
            ("video_compare", "Video Compare"),
            ("multi_compare", "Multi Compare"),
        )
    ]
    button = _Button()
    presenter = SimpleNamespace(
        store=SimpleNamespace(settings=SimpleNamespace(current_language="ru")),
        main_controller=SimpleNamespace(
            workspace=SimpleNamespace(
                list_session_blueprints=lambda: tuple(blueprints)
            )
        ),
        ui=SimpleNamespace(btn_new_session=button),
    )

    configure_workspace_actions(presenter)

    assert button.actions == [
        ("Сравнение изображений", "image_compare"),
        ("Сравнение видео", "video_compare"),
        ("Мульти-сравнение", "multi_compare"),
    ]
