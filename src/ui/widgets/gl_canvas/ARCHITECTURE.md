# GL Canvas — Architecture Plan

## Типы режимов

**Split-режимы** (обе текстуры видны одновременно через шейдер):
- Обычный split
- Edges split (CPU генерирует edge-карты → те же две текстуры)

**Diff-режимы** (один выходной результат, texture0):
- Highlight diff
- Grayscale diff
- SSIM map

**Каналы** (R / G / B / L / RGB) — uniform в шейдере, CPU не задействован.

---

## Целевая структура файлов

```
gl_canvas/
  __init__.py
  widget.py              # координатор ~100 строк
  render_context.py      # единое состояние рендера (dataclass)
  layers/
    base.py              # AbstractLayer (initialize / render / resize / cleanup)
    background.py        # split + diff-результат + каналы
    divider.py           # линия-разделитель
    magnifier.py         # CPU патч → текстура + шейдер
    guides.py            # прицел (crosshair) + кольцо захвата
    text_overlay.py      # названия файлов (QPainter → текстура)
  processors/
    channel.py           # R/G/B/L (или уходит полностью в шейдер)
    diff.py              # highlight, grayscale, ssim, edges (CPU)
  shaders/
    background.frag
    divider.frag
    guides.frag
    magnifier.frag
```

---

## Что на GPU, что на CPU

| Задача            | Где                | Почему                                              |
|-------------------|--------------------|-----------------------------------------------------|
| Канал R/G/B/L     | GPU шейдер         | Trivial GLSL, убирает CPU-пересчёт при движении     |
| Split rendering   | GPU                | Уже есть                                            |
| Divider / guides  | GPU геометрия      | Простые линии                                       |
| Лупа — композитинг| GPU шейдер         | Круглая маска, zoom patch → текстура                |
| Лупа — контент    | CPU → текстура     | Нужен оригинал в полном разрешении                  |
| Highlight diff    | CPU → текстура     | Пороговая маска, статичен при неизменных изображениях|
| Grayscale diff    | CPU → текстура     | Статичен, autocontrast сложен на GPU               |
| SSIM              | CPU → текстура     | skimage, не реалтайм                                |
| Edges             | CPU → 2 текстуры   | Потом обычный split shader                          |
| Текст (имена)     | CPU QPainter → tex | Шрифты, переносы                                    |

---

## Шейдер background.frag (ключевое)

```glsl
uniform int channelMode;   // 0=RGB 1=R 2=G 3=B 4=L
uniform int renderMode;    // 0=split  1=single (diff result)

vec4 applyChannel(vec4 c) {
    if (channelMode == 1) return vec4(c.r, 0.0, 0.0, c.a);
    if (channelMode == 2) return vec4(0.0, c.g, 0.0, c.a);
    if (channelMode == 3) return vec4(0.0, 0.0, c.b, c.a);
    if (channelMode == 4) {
        float l = dot(c.rgb, vec3(0.299, 0.587, 0.114));
        return vec4(l, l, l, c.a);
    }
    return c;
}

void main() {
    if (renderMode == 1) {
        FragColor = texture(image1, uv);  // diff — один результат
        return;
    }
    vec4 color = coord < splitPosition
        ? applyChannel(texture(image1, uv))
        : applyChannel(texture(image2, uv));
    FragColor = color;
}
```

---

## Поток данных

```
Смена изображений / diff-режима
  └─► processors/diff.py (фоновый поток)
        └─► загрузить в texture0 (или 0+1 для split)
              └─► update() → шейдер читает

Смена канала / split_pos / zoom / pan
  └─► обновить uniform
        └─► update() — только GPU, CPU не задействован
```

---

## Порядок реализации

1. **Лупа на шейдеры** ← _начинаем здесь_
   - CPU генерирует patch лупы → texture2
   - Шейдер рисует круглую маску поверх background
   - Убираем CPU-композитинг лупы из pipeline

2. **Каналы в шейдер** (channelMode uniform)
   - Убираем `extract_channel` из CPU pipeline
   - Мгновенное переключение без перерасчёта

3. **Divider / guides как геометрия** (DividerLayer, GuidesLayer)

4. **Diff-режимы** (processors/diff.py → текстура)

5. **Текст** (TextOverlayLayer)

6. **Рефакторинг widget.py** → layers + render_context
