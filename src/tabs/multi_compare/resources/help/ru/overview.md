## Обзор мультисравнения

Сравнивайте много изображений в одной сессии: сетка, дроп по слотам и режим фокуса.

### Открыть сессию {#open-session}

Выберите {{tr:workspace.session_types.multi_compare}} в выборе сессии или {{tr:action.workspace.new_multi_compare}} через {{tr:menu.find_action}} (`Ctrl+Shift+P`). См. также [Вкладки рабочей области](help://session_picker).

### Раскладки и разрез по зазору {#layouts}

- **Сетка** — слоты; бросайте файлы в ячейку или {{tr:multi_compare.action.add_images}} (`Ctrl+O`).
- **Пустые слоты** — остаются для новых дропов.
- **Разрез по зазору** — бросок в зазор между ячейками режет слот и создаёт новую ячейку рекурсивно.
- **Веса** — тяните разделители сетки, чтобы менять доли.
- **Смена раскладки** — по возможности сохраняет загруженные изображения.

:::figure{side=block width=320}
![Сетка мультисравнения]({{img:workspace.multi_compare.overview.layouts}})
{{tr:workspace.session_types.multi_compare}} — сетка / разрез по зазору.
:::

### Режим фокуса {#focus-mode}

- **Вход** — двойной клик по слоту на весь холст.
- **Выход** — `Esc` возвращает к сетке.
- **Навигация** — зум и пан как в {{tr:workspace.session_types.image_compare}}; см. [Навигацию по холсту](help://view_navigation).

### Сетка и подписи {#grid-and-labels}

- **Видимость** (`D`) — {{tr:multi_compare.action.divider_visible}}.
- **Цвет / ширина** — {{tr:multi_compare.action.divider_color}} и {{tr:multi_compare.action.divider_width}}.
- **Текст подписей** — {{tr:multi_compare.action.text_settings}} открывает стиль (без радио размещения из {{tr:workspace.session_types.image_compare}}).

### Контекстное меню слота {#context-menu}

Правый клик по слоту — действия для изображения, в том числе [Свойства изображения](help://image_properties) (метаданные файла и позиция слота) и **Переместить** (ghost → клик по другой вкладке запускает размещение как при DnD / вставке).

### Сохранение и экспорт {#save-and-export}

- **Быстрое сохранение** (`Ctrl+S`) — {{tr:multi_compare.action.quick_save}}.
- **Диалог** — {{tr:multi_compare.action.save}} (панель или {{tr:menu.find_action}}).
- **Паритет** — экспорт как на экране (раскладка, подписи, линии), не одиночный разрез {{tr:workspace.session_types.image_compare}}.

Ищите сохранение и экспорт в {{tr:menu.find_action}}, пока вкладка {{tr:workspace.session_types.multi_compare}} в фокусе.
