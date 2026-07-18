## Свойства изображения

Просмотр метаданных файла и контекста в приложении для одного загруженного изображения, не покидая сессию.

### Открыть диалог {#open}

Правый клик по строке списка {{tr:workspace.session_types.image_compare}} или по слоту {{tr:workspace.session_types.multi_compare}} → {{tr:image_properties.title}}. Диалог только для чтения, кроме {{tr:image_properties.copy_all}} — копирует все видимые строки в буфер обмена.

:::figure{side=block width=280}
![Диалог свойств изображения]({{img:platform.image_properties.open}})
{{tr:image_properties.title}}.
:::

### Разделы {#sections}

Строки сгруппированы так:

- {{tr:image_properties.section_file}} — имя, путь, размер на диске, формат, время изменения
- {{tr:image_properties.section_image}} — размер в пикселях, пропорции, ориентация, каналы, режим / профиль цвета, если есть
- {{tr:image_properties.section_app}} — как приложение разместило изображение в текущей сессии (ниже)
- {{tr:image_properties.section_metadata}} — поля камеры / EXIF, если файл их отдаёт

Пустые значения остаются пустыми; ошибка чтения файла показывается как {{tr:image_properties.read_error}}.

### Контекст в приложении {#in-app}

{{tr:image_properties.section_app}} зависит от типа сессии. В сессии {{tr:workspace.session_types.image_compare}} могут быть {{tr:image_properties.side}} (лево / право) и {{tr:image_properties.rating}}. В {{tr:workspace.session_types.multi_compare}} — {{tr:image_properties.position}} или {{tr:image_properties.slot}} для ячейки. Эти строки описывают состояние сессии, а не файл на диске.

### Закрытие {#close}

{{tr:image_properties.close}} закрывает диалог. Списки, рейтинги и холст при этом не меняются.
