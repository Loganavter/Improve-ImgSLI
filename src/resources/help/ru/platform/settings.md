## Настройки

Настройки сгруппированы по задачам — общие, внешний вид, производительность, анализ и клавиатура — чтобы менять одно за раз.

### Открыть настройки {#open-settings}

- **Меню / шестерёнка** — {{tr:menu.settings}} или шестерёнка на тулбаре.
- **{{tr:menu.find_action}}** — `Ctrl+Shift+P` и имя страницы ({{tr:settings.general}}, {{tr:settings.appearance}}, {{tr:settings.keyboard}}, …).
- **{{tr:action.palette.learn_more}}** — у действия настроек открывает эту страницу с якорем, если тег задан.

### Общие {#general}

- **{{tr:label.language}}** — en / ru / zh / pt_BR.
- **{{tr:label.theme}}** — auto / light / dark.
- **{{tr:settings.system_notifications}}** — опциональные уведомления после сохранения.
- **{{tr:settings.enable_debug_logging}}** — подробные логи для отладки.
- **{{tr:settings.show_workspace_tabs}}** — показать или скрыть полоску вкладок сессий.

### Внешний вид {#interface}

- **{{tr:settings.ui_mode}}** — {{tr:settings.ui_mode_beginner}} / {{tr:settings.ui_mode_advanced}} / {{tr:settings.ui_mode_expert}}.
- **{{tr:settings.ui_font}}** — встроенный, системный или свой шрифт.
- **Лимиты** — например максимальная длина отображаемого имени.

### Производительность {#performance}

- **{{tr:settings.render_backend_label}}** — зависит от платформы; может потребоваться перезапуск.
- **{{tr:settings.display_cache_resolution}}** — лимит основного превью; лупа и экспорт берут оригинал (сессия {{tr:workspace.session_types.image_compare}}).
- **Интерполяция** — качество ресемплинга зума / лупы / лазера.
- **{{tr:settings.optimize_magnifier_movement}}** — более плавное движение лупы (метод интерполяции — на той же странице).
- **{{tr:settings.magnifier_intersection_highlight}}** — подсветка пересечения линз.
- **{{tr:settings.magnifier_auto_color_new_instances}}** — разные цвета для новых линз.
- **{{tr:settings.recording_fps}}** — частота захвата для [Видеоредактора](help://video).

### Анализ {#analysis}

Только для сессии {{tr:workspace.session_types.image_compare}}:

- **{{tr:settings.autocrop_black_borders_on_load}}** — обрезать чёрные поля при загрузке.
- **Авто {{tr:ui.psnr}} / {{tr:ui.ssim}}** — под холстом (по умолчанию выкл.).

Страница появляется, когда вкладка {{tr:workspace.session_types.image_compare}} вносит свою секцию.

### Клавиатура {#keyboard}

- **Переназначение** — поиск действий; аккорды по группам platform / {{tr:workspace.session_types.image_compare}} / {{tr:workspace.session_types.multi_compare}}.
- **Сброс** — одного ярлыка или всех.
- **Фиксированные** — `WASD` и `Space` на холсте не ремапятся — см. [Горячие клавиши](help://hotkeys).
