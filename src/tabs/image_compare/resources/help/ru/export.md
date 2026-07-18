## Экспорт

Сохраните то, что видно, как кадр. Запись и видеоредактор — отдельная тема: [Видеоредактор](help://video).

### Сохранить кадр {#saving-an-image}

{{tr:image_compare.action.save}} (панель или {{tr:menu.find_action}}) открывает диалог экспорта.

- **Путь** — каталог и имя файла.
- **Формат** — PNG, JPEG, WEBP, BMP, TIFF или JXL.
- **Превью** — панель показывает собранный результат до записи на диск.

:::figure{side=block width=630}
![Диалог экспорта]({{img:workspace.image_compare.export.dialog}})
{{tr:image_compare.action.breadcrumb.toolbar}} → {{tr:image_compare.action.breadcrumb.export}}.
:::

### Разрешение и качество {#resolution-and-quality}

- **Размер** — ширина и высота, если известен источник; фиксация пропорций.
- **Качество** — {{tr:label.quality}} для lossy-форматов.
- **PNG** — уровень сжатия и {{tr:export.optimize_png}}.
- **Заливка** — у прозрачных форматов {{tr:export.fill_background}} доступна, только если виртуальный холст выходит за `0..1` (поля лупы / uncrop). На unit-сцене опция выключена.

### Метаданные и избранное {#metadata-and-favorites}

- **Метаданные** — {{tr:export.include_metadata}}; комментарий и {{tr:export.remember_by_default}}.
- **Избранное** — {{tr:misc.set_as_favorite}} / {{tr:tooltip.use_favorite}} после выбора каталога.
- **Подписи** — если включены {{tr:image_compare.action.file_names}}, имена могут попасть в кадр.

### Быстрое сохранение {#quick-save}

- **`Ctrl+S`** — {{tr:image_compare.action.quick_save}} с последними настройками.
- **Трей** — опционально в [Настройки → Общие](help://settings#general).

### Запись и видео {#video-editor}

Чтобы записать сессию и закодировать видео или GIF, см. [Видеоредактор](help://video). Кадры и видео сохраняют паритет с живым холстом (включая режимы разницы).
