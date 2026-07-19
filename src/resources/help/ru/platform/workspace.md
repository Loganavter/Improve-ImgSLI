## Вкладки рабочей области и выбор сессии

Управляйте сессиями в полоске вкладок и открывайте типы сравнения со стартовой страницы выбора сессии.

### Выбор сессии {#session-picker}

- **Открыть** — {{tr:action.workspace.open_session_picker}} (или кнопка новой вкладки).
- **Выбрать** — карточку {{tr:workspace.session_types.image_compare}} или {{tr:workspace.session_types.multi_compare}}.
- **Недавние** — недавние проекты ``.imgsli`` (сетка или список, сортировка по дате или имени). Клик открывает проект. На карточке показывается превью холста из ``preview.png`` внутри проекта (старые пакеты с ``preview.jpg`` тоже читаются; иначе — иконка типа сессии). Перетащите файл проекта на панель, чтобы добавить его в список без открытия. ПКМ — убрать из списка или показать в папке.

:::figure{side=block width=420}
![Выбор сессии]({{img:platform.workspace.session_picker}})
{{tr:action.workspace.open_session_picker}} — {{tr:workspace.session_types.image_compare}} / {{tr:workspace.session_types.multi_compare}}.
:::

### Открыть сессию без выбора {#new-session-actions}

Через {{tr:menu.find_action}} (`Ctrl+Shift+P`):

- {{tr:action.workspace.new_image_compare}}
- {{tr:action.workspace.new_multi_compare}}

{{tr:action.workspace.open_session_picker}} возвращает на стартовую страницу, когда удобнее выбрать визуально.

### Полоска вкладок {#tab-strip}

- **Переключить** — клик по вкладке.
- **Закрыть** — удаляет сессию; если она была последней, открывается выбор сессии вместо выхода.
- **Контекстное меню** — переименовать, закрыть или закрыть остальные.

### Переименовать вкладку {#rename}

Пункт переименования в контекстном меню: введите имя и подтвердите. Автозаголовки остаются языковыми, пока вы не зададите своё имя.

### Дальше по темам {#next-topics}

Короткие сценарии: [С чего начать](help://introduction). Инструменты сессии: [Сравнение](help://comparison) или [{{tr:workspace.session_types.multi_compare}}](help://multi_compare).
