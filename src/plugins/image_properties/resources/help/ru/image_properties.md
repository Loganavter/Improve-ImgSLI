## Свойства изображения

Метаданные файла и контекст в приложении для одного загруженного изображения. Диалог висит над сессией и ничего в ней не меняет.

### Открыть диалог {#open}

Пункт {{tr:image_compare.action.context_properties}} в контекстном меню списка или слота открывает {{tr:image_properties.title}} для этого изображения.

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

Строки без значений пропускаются; ошибка чтения файла показывается как {{tr:image_properties.read_error}}.

### Контекст в приложении {#in-app}

{{tr:image_properties.section_app}} зависит от типа сессии. Запись {{tr:workspace.session_types.image_compare}} несёт {{tr:image_properties.side}} (лево / право) и {{tr:image_properties.rating}}. Ячейка {{tr:workspace.session_types.multi_compare}} несёт {{tr:image_properties.position}}. Эти строки описывают состояние сессии, а не файл на диске.

### Закрытие {#close}

{{tr:image_properties.close}} закрывает диалог. {{tr:image_properties.copy_all}} копирует все видимые строки в буфер обмена; у отдельных строк есть своё копирование.
