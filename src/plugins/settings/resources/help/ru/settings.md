## Настройки

Поведение приложения в одном диалоге: встроенные страницы плюс секции вкладок рабочей области (анализ сравнения, AI-данные галереи). Секции вкладок видны всегда, независимо от активной сессии.

### Открыть настройки {#open-settings}

- **Меню** — {{tr:menu.settings}} (`Ctrl+,`).
- **Панель** — кнопка-шестерёнка.
- **{{tr:menu.find_action}}** — `Ctrl+Shift+P` и имя страницы ({{tr:settings.general}}, {{tr:settings.appearance}}, {{tr:settings.keyboard}}, …).
- **{{tr:action.palette.learn_more}}** — у действия настроек открывает подходящий якорь, если тег задан.

### Поиск в настройках {#search}

Поле поиска над списком разделов: совпадения идут по одной строке на раздел, независимо от глубины совпадения (имя элемента, название группы, любой язык). Выбор строки открывает раздел с пульсацией найденных опций. `Esc` очищает поиск и возвращает полный список. Список разделов растягивается.

### Общие {#general}

- **{{tr:label.language}}** — en / ru / zh / pt_BR.
- **{{tr:label.theme}}** — auto / light / dark.
- **{{tr:settings.system_notifications}}** — переключатель уведомлений ОС.
- **{{tr:settings.enable_debug_logging}}** — подробные логи для отладки.

### Внешний вид {#interface}

- **{{tr:settings.ui_mode}}** — радиокнопки {{tr:settings.ui_mode_beginner}} / {{tr:settings.ui_mode_advanced}} / {{tr:settings.ui_mode_expert}}; по умолчанию новичок, сюда же попадает выбор первого запуска.
- **{{tr:settings.ui_font}}** — встроенный, системный или свой шрифт.
- **{{tr:settings.ui_scale}}** — масштаб интерфейса (0.5–2.5).
- **Лимиты** — например максимальная длина отображаемого имени.

### Производительность {#performance}

- **{{tr:settings.render_backend_label}}** — доступные бэкенды зависят от платформы; смена может потребовать перезапуск.

### {{tr:workspace.session_types.image_compare}} {#image_compare}

Параметры сравнения, доступны всегда:

- **Интерполяция** — качество ресемплинга зума / лупы / лазера.
- **{{tr:settings.optimize_magnifier_movement}}** — плавное движение лупы, метод интерполяции — в той же строке.
- **{{tr:settings.magnifier_intersection_highlight}}** — подсветка пересечения линз.
- **{{tr:settings.magnifier_auto_color_new_instances}}** — разные цвета новых линз.
- **{{tr:image_compare.settings.recording_fps}}** — частота захвата для [Видеоредактора](help://video).
- **{{tr:settings.autocrop_black_borders_on_load}}** — обрезка чёрных полей при загрузке.
- **Авто {{tr:ui.psnr}} / {{tr:ui.ssim}}** — автоматический подсчёт метрик, по умолчанию выключен.

### Клавиатура {#keyboard}

- **Переназначение** — ярлыки по владельцам: platform / {{tr:workspace.session_types.image_compare}} / {{tr:workspace.session_types.multi_compare}}.
- **Сброс** — одного ярлыка или всех.
- **Фиксированные** — `WASD` и `Space` на холсте не ремапятся — см. [Горячие клавиши](help://hotkeys).
