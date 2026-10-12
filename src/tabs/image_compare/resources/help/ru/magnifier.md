## Лупа

Лупа берёт область пары и показывает увеличенный вид на холсте — локальная деталь за пределами линии раздела.

### Включение {#enabling}

- **Включить** — {{tr:image_compare.action.magnifier}} на тулбаре или `M`.
- **Поставить** — клик или перетаскивание по изображению задаёт зону захвата (красный круг).
- **Кольцо** — размер и цвет кольца захвата совпадают с оформлением лупы.

:::figure{side=block width=280}
![Линза лупы]({{img:workspace.image_compare.magnifier.enabling}})
{{tr:image_compare.action.breadcrumb.toolbar}} → {{tr:image_compare.action.breadcrumb.magnifier}}.
:::

### Размер и движение {#size-and-movement}

- **Размер линзы** — {{tr:image_compare.label.magnifier_size}}.
- **Размер захвата** — {{tr:image_compare.label.capture_size}} (сколько исходной области сэмплируется).
- **Движение** — `WASD` при активной линзе; `QE` меняет расстояние половинок.
- **Скорость** — на панели лупы, когда она видна.

### Заморозка {#freeze}

{{tr:image_compare.action.freeze}} (`F`) фиксирует линзу на экране; движение с клавиатуры продолжает работать, пока указатель свободен.

### Разделитель, направляющие и цвета {#guides-and-colors}

- **Ориентация** — {{tr:image_compare.action.magnifier_orientation}}.
- **Внутренний разделитель** — {{tr:image_compare.action.magnifier_divider_combined}} (скролл / ПКМ).
- **Видимость** — {{tr:image_compare.action.magnifier_divider_visible}} и {{tr:image_compare.action.magnifier_guides}}, плюс их толщина.
- **Цвета** — {{tr:image_compare.action.magnifier_colors}} для оформления экземпляра.

### Несколько экземпляров {#instances}

- **Добавить / убрать** — {{tr:image_compare.action.magnifier_instances}}, чтобы смотреть несколько областей.
- **Авто-цвет** — новые экземпляры могут получать разные цвета, если это включено в настройках.

### Объединённый режим {#combined-mode}

- **Слияние** — когда обе половинки видимы, а расстояние между ними сходится к порогу объединения, они становятся одной линзой.
- **Внутренний раздел** — тяните `ПКМ` внутри линзы.
- **Превью стороны** — `Space+Shift` форсирует сторону внутри объединённой линзы.

:::figure{side=block width=280}
![Объединённая лупа]({{img:workspace.image_compare.magnifier.combined_mode}})
{{tr:image_compare.action.magnifier}} — объединённый режим.
:::

Для сравнения на всём холсте без линзы см. [Сравнение](help://comparison).

### Настройки, влияющие на лупу {#related-settings}

Связанные с лупой опции — в [Настройках](help://settings#image_compare):

- Оптимизация движения лупы и её интерполяция
- Подсветка пересечений линз
- Авто-цвет новых экземпляров
