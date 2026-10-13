## Экспорт

Экспорт текущего холста как статичного изображения. Захват сессии и кодирование видео — отдельная тема: [Видеоредактор](help://workspace.image_compare.video).

### Сохранить кадр {#saving-an-image}

{{tr:image_compare.action.save}} (панель или {{tr:menu.find_action}}) открывает диалог экспорта.

- **Путь** — каталог и имя файла.
- **Формат** — PNG, JPEG, WEBP, BMP, TIFF или JXL.
- **Превью** — панель показывает собранный результат до записи.

:::figure{side=block width=630}
![Диалог экспорта](../assets/export_dialog.jpg)
{{tr:image_compare.action.breadcrumb.toolbar}} → {{tr:image_compare.action.breadcrumb.export}}.
:::

### Разрешение и качество {#resolution-and-quality}

- **Размер** — поля ширины и высоты с фиксацией пропорций.
- **Качество** — {{tr:label.quality}} показывается только для lossy-форматов.
- **PNG** — уровень сжатия и {{tr:export.optimize_png}}.
- **Заливка** — {{tr:export.fill_background}} закрашивает поля, если виртуальный холст выходит за `0..1`. На unit-холсте опция выключается.

### Метаданные и избранное {#metadata-and-favorites}

- **Метаданные** — {{tr:export.include_metadata}} включены, пока не выключены; поле комментария скрывается вместе с ними. {{tr:export.remember_by_default}} сохраняет текст комментария для следующего экспорта.
- **Избранное** — {{tr:misc.set_as_favorite}} закрепляет текущий каталог; {{tr:tooltip.use_favorite}} возвращает его.
- **Подписи** — если включены {{tr:image_compare.action.file_names}}, имена попадают в кадр как состояние сессии, а не данные файла.

### Быстрое сохранение {#quick-save}

- **`Ctrl+S`** — {{tr:image_compare.action.quick_save}} повторяет последние настройки экспорта без открытия диалога.
- **Трей** — меню иконки в трее заново открывает последний сохранённый файл и папку.

### Запись и видео {#video-editor}

Элементы записи и кодирование видео/GIF — в [Видеоредакторе](help://workspace.image_compare.video).
