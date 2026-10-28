<p align="center">
  <img src="src/resources/icons/blinktable-logo.svg" alt="BlinkTable" width="384">
</p>

<h1 align="center">BlinkTable</h1>

<p align="center">
  <a href="https://github.com/Loganavter/Improve-ImgSLI/releases/latest"><img src="https://img.shields.io/github/v/release/Loganavter/Improve-ImgSLI?style=flat-square"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/Loganavter/Improve-ImgSLI?style=flat-square"></a>
  <a href="https://github.com/Loganavter/Improve-ImgSLI/releases"><img src="https://img.shields.io/github/downloads/Loganavter/Improve-ImgSLI/total?style=flat-square" alt="GitHub Downloads"></a>
  <a href="https://flathub.org/apps/details/io.github.Loganavter.Improve-ImgSLI"><img src="https://img.shields.io/flathub/downloads/io.github.Loganavter.Improve-ImgSLI?style=flat-square" alt="Flathub Downloads"></a>
</p>

<p align="center">Рабочее пространство для сравнения изображений и кадров видео.</p>

<p align="center">Read this in other languages: <a href="readme.md">English</a></p>

## Что это

Приложение открывается на выборе сессии и работает во вкладках трёх видов.
Image Compare ставит два изображения рядом. Multi Compare синхронизирует любое
количество изображений в одной сцене. Image Gallery разбирает, измеряет и
оценивает целые папки. У каждой вкладки свой холст, состояние, справка и путь
экспорта.

## Сравнение

- Разделитель, панорамирование и зум на GPU: горизонтальный или вертикальный
  сплит, синхронный зум по сторонам, режимы каналов, полноэкранный фокус на
  одной ячейке.
- Лупы, двойные или совмещённые, со своим управлением сплитом, сэмплингом EWA
  Lanczos, режимом заморозки и направляющими. Луп можно поставить сколько
  угодно; у каждой свои область, положение, размер и цвета.
- <kbd>Space</kbd> с кнопкой мыши показывает предпросмотр одного изображения.
- Любая поверхность доступна с клавиатуры. WASD и QE ведут навигацию,
  <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> открывает Find Action, где любая
  команда запускается по имени.

## Измерения

- Режимы разницы: подсветка, оттенки серого, края, карта SSIM.
- PSNR и SSIM для каждой пары изображений.
- AI-оценка отправляет сравниваемые изображения модели зрения и возвращает балл
  по каждой оси вместе с вердиктом; ключ задаётся в Settings → AI. Результаты
  кешируются по бэкенду, поэтому смена модели или эндпоинта запускает новый
  разбор вместо показа старых баллов.
- Вопрос к AI по карточке или выделению: ответ остаётся в границах выбранного.
- Разбор галереи: сортировка, ранжирование, отклонить или оставить, группировка
  серий, сброс кешей метрик, Clean Review.

## Экспорт

- Экспорт изображения пишет собранную сцену: разделители, лупу, оверлеи и
  оформленные имена файлов ровно так, как они видны. PNG, JPEG, WEBP, BMP, TIFF,
  JXL.
- Запись сессии в видеоредакторе: обрезка и удаление участков, ключевые
  состояния, экспорт в MP4, WebM, AVI, GIF, ProRes или AV1.
- Задачи экспорта показывают прогресс и отменяются, не оставляя мёртвую строку в
  списке.

## Рабочее пространство

- Окно с вкладками в стиле Firefox; при запуске открывается выбор сессии.
- Файлы проектов (`.blinktable`; старые `.imgsli` тоже открываются) держат
  вместе изображения, разделители, лупы и видеосессии.
- Интерфейс рисует собственный тулкит проекта, без QSS: светлая и тёмная темы,
  свои шрифты, живой масштаб интерфейса от 0.5 до 2.5×, который пересчитывает
  геометрию вместо растягивания.
- Английский, русский, китайский и бразильский португальский; интеграция с
  треем, уведомления о сохранении, лаунчер для запуска из исходников и
  автообрезка.

## Управление из агента

Канал управления (`BLINKTABLE_CONTROL=1`) и MCP-сервер дают 23 инструмента: опись
элементов, чтение Store, действий, лога и трейсера, клики, нажатия клавиш, обход
секций с клавиатуры, список и отмена задач, смена темы или языка, снимок
поверхности и ожидание асинхронного состояния вместо опроса.

Каждый результат говорит, пришёл ли он из живого экземпляра. Снимки сообщают
свой метод и число слоёв холста, а достижимость с клавиатуры измеряется
(`ui_nav_state` вместе с `nav_key`). Справочник:
[docs/dev/MCP.md](docs/dev/MCP.md).

## Установка

| Платформа | Как |
|---|---|
| Windows | установщик из [Releases](https://github.com/Loganavter/Improve-ImgSLI/releases/latest) |
| Linux (Flatpak) | `flatpak install io.github.Loganavter.Improve-ImgSLI`, затем `flatpak run io.github.Loganavter.Improve-ImgSLI` |
| Linux (AUR) | `yay -S improve-imgsli` |
| Из исходников | `git clone … && cd Improve-ImgSLI && ./launcher.sh run` |

Полная инструкция: [docs/INSTALL.md](docs/INSTALL.md), справочник по лаунчеру:
[docs/LAUNCHER.md](docs/LAUNCHER.md).

Изображения больше `65536 px` по стороне отклоняются на ограниченном пути
декодирования; потоковое декодирование такого ограничения не имеет. Экспорт
неподвижного изображения больше `16384 px` предупреждает, что путь не проверен.

## Первые пять минут

1. Запустите приложение. Откроется выбор сессии; выберите Image Compare, Multi
   Compare или Image Gallery, и она станет отдельной вкладкой.
2. Нажмите <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd>. Find Action запускает
   любую команду по имени, а "Learn more" открывает соответствующий раздел
   справки.
3. В Image Compare добавьте изображения кнопкой или перетаскиванием. Двигайте
   разделитель, масштабируйте колесом, а с <kbd>Space</kbd> и кнопкой мыши
   смотрите предпросмотр одной стороны.
4. Откройте лупу, выберите интерполяцию, настройте зум и экспортируйте собранную
   сцену.
5. В галерее направьте разбор на папку: метрики для каждой пары и AI-оценка,
   когда задан ключ.

Горячие клавиши, настройки и полный сценарий работы лежат во встроенной справке
(меню Help). Исходники: [EN host topics](src/resources/help/en/) ·
[RU](src/resources/help/ru/) ·
[Image Compare](src/tabs/image_compare/resources/help/en/) ·
[Multi Compare](src/tabs/multi_compare/resources/help/en/) ·
[Gallery](src/tabs/image_gallery/resources/help/en/).

## Документация

| Что нужно | Что читать |
|---|---|
| Установка и лаунчер | [docs/INSTALL.md](docs/INSTALL.md), [docs/LAUNCHER.md](docs/LAUNCHER.md) |
| Управление приложением из агента | [docs/dev/MCP.md](docs/dev/MCP.md) |
| Участие в разработке | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Архитектура, контракты, паттерны | [docs/dev/ARCHITECTURE.md](docs/dev/ARCHITECTURE.md), [docs/dev/CONTRACTS.md](docs/dev/CONTRACTS.md) |
| Замысел и история проекта | [VISION.md](VISION.md), [docs/DEVELOPMENT_HISTORY.md](docs/DEVELOPMENT_HISTORY.md) |
| Открытый технический долг | [docs/dev/TODO.md](docs/dev/TODO.md) |

## Участие

Установка, правила кода и упаковка описаны в [CONTRIBUTING.md](CONTRIBUTING.md).
Issues и pull requests идут через GitHub.

## Сопровождающие

<table>
  <tr>
    <td align="center" valign="top" width="140">
      <a href="https://github.com/nebulosa2007" title="GitHub profile">
        <img src="https://github.com/nebulosa2007.png?size=100" alt="Nebulosa's Avatar" width="100" style="border-radius: 50%;"><br/>
        <sub><b>Nebulosa</b></sub>
      </a>
    </td>
    <td valign="top">
      <strong>Сопровождающий пакета AUR</strong>
      <p>Nebulosa ведёт пакет <a href="https://aur.archlinux.org/packages/improve-imgsli">Arch Linux (AUR)</a> с самого начала проекта: правки упаковки и работа над стабильностью в экосистеме Arch.</p>
      <a href="https://github.com/nebulosa2007"><img src="https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub"></a>
      <a href="https://aur.archlinux.org/account/Nebulosa"><img src="https://img.shields.io/badge/AUR-1793D1?style=for-the-badge&logo=arch-linux&logoColor=white" alt="AUR Profile"></a>
    </td>
  </tr>
</table>

## Лицензия

GPL-3.0-or-later, см. [LICENSE](LICENSE). Зависимости времени выполнения, включая
PySide6/Qt под LGPL-3.0-or-later, перечислены в
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

## История звёзд

![Star History Chart](https://api.star-history.com/svg?repos=Loganavter/Improve-ImgSLI&type=Timeline)
