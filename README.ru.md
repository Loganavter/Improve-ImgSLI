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

<p align="center"><strong>BlinkTable — рабочее пространство для серьёзного сравнения изображений и видео: сравнивайте, измеряйте, доказывайте качество.</strong></p>

<p align="center">Read this in other languages: <a href="readme.md">English</a></p>

## Что это

BlinkTable открывается на выборе сессии и даёт независимые вкладки-воркспейсы:
**Image Compare** на два изображения, синхронизированный **Multi Compare** на любое
число изображений и **Image Gallery** для разбора, измерений и AI-оценки целых папок.
Каждая вкладка владеет своим холстом, состоянием, справочными страницами и экспортом.

Это не просмотрщик с ползунком. Сравнение — и есть продукт: сплит, зум, лупы,
режимы различий, объективные метрики, запись сессии в видео и экспорт ровно того,
что видно на экране.

## Чем отличается

- **Сравнение в первую очередь.** Сплит, панорамирование и зум, несколько луп,
  навигация WASD/QE и мгновенный предпросмотр одного изображения — основные
  взаимодействия, а не настройки, спрятанные в меню.
- **Анализ, а не «на глаз».** Режимы различий highlight / grayscale / edges / SSIM,
  метрики PSNR + SSIM по паре и опциональная **AI-оценка качества** (VLM), которая
  оценивает папку по нескольким осям, плюс **Ask AI** по выделению.
- **Экспорт без расхождений.** Экспортируется именно собранный вид: сплиттеры,
  оверлеи, лупы, оформленные имена — включая экспорт видео записанной сессии.
- **Клавиатура и агенты.** Каждая поверхность достижима с клавиатуры, а запущенный
  экземпляр можно вести LLM-агентом через встроенный **MCP / канал управления**
  (инвентарь элементов, клики, клавиши, захваты, логи).

## Предпросмотр

<div align="center">
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/2.0.0/Improve_ImgSLI/screenshots/screenshot_1.jpg" width="70%">
</div>

---

## Возможности

### Сравнение

- **Вкладки Image Compare / Multi Compare** — два изображения рядом или любое число
  изображений в одной сцене с перетаскиваемыми слотами и свободно меняющимися разделителями.
- Плавный GPU-зум и панорамирование, горизонтальный/вертикальный сплит,
  синхронизация зума по сторонам, режимы каналов, полноэкранный фокус для любой ячейки.
- **Лупы** — двойная или объединённая, внутренний сплит, субпиксельно-стабильный
  рендер, EWA Lanczos, режим заморозки, направляющие «лазеры»; луп может быть
  несколько, у каждой своя область, позиция, размер, цвета и заморозка.
- Мгновенный предпросмотр одного изображения: <kbd>Space</kbd> + кнопки мыши.

### Анализ

- Режимы различий: **highlight, grayscale, edge comparison, SSIM map**; метрики
  PSNR/SSIM для объективной проверки.
- **AI-оценка качества** — VLM читает сравниваемые изображения и возвращает баллы
  по осям и вердикт; нужен ключ API в **Настройки → AI**. Результаты кэшируются
  по бэкенду, поэтому смена модели или адреса приводит к переанализу, а не к
  показу устаревших оценок.
- **Ask AI** по карточке или выделению — ответ в рамках выбранного.
- Разбор в галерее: сортировка, ранжирование, отклонение/возврат, группировка серий,
  сброс кэшей метрик, Clean Review.

### Запись и экспорт

- **Экспорт WYSIWYG**: сплиттеры, лупа, оверлеи и оформленные имена ровно как
  собрано — PNG, JPEG, WEBP, BMP, TIFF, JXL (JXL пишется через бэкенд
  imagecodecs из обоих табов сравнения; если бэкенда в сборке нет, формат
  просто не предлагается в диалоге).
- **Запись сессии + видеоредактор**: запись сравнения, обрезка и удаление участков
  таймлайна, ключевые состояния, экспорт в MP4, WebM, AVI, GIF, ProRes, AV1.
- Задачи экспорта показывают прогресс и отменяются, не оставляя «висящих» строк.

### Платформа и интерфейс

- **Вкладки-воркспейсы** с таббаром в стиле Firefox, выбор сессии на старте, файлы
  проекта (`.blinktable`; старые `.imgsli` открываются), которые хранят изображения, сплиттеры, лупы и видео-сессии.
- Собственный **отрисованный тулкит** (без QSS): светлая/тёмная тема, свои шрифты,
  живой масштаб интерфейса (0.5–2.5×), который пересчитывает геометрию, а не растягивает её.
- Четыре языка интерфейса (EN / RU / ZH / pt_BR), интеграция с треем, уведомления
  о сохранении, лаунчер для запуска из исходников, надёжный автокроп.

### Управление агентом (MCP)

- Живой **канал управления** (`IMGSLI_CONTROL=1`) и MCP-сервер: 23 инструмента —
  инвентарь элементов, чтение Store/действий/логов/трейсера, клики, клавиши,
  навигация по клавиатурным секциям, список и отмена задач, тема/язык, захват
  поверхностей и **ожидание** асинхронного состояния вместо ручных опросов.
- Рассчитан на честную инструментовку: каждый результат говорит, пришёл ли он от
  живого экземпляра, захваты несут метод и число слоёв канваса, а достижимость
  клавиатурой измеряется (`ui_nav_state` + `nav_key`), а не предполагается.
- Начать: [docs/dev/MCP.md](docs/dev/MCP.md).

---

## Установка

| Платформа | Как |
|---|---|
| Windows | установщик из [Releases](https://github.com/Loganavter/Improve-ImgSLI/releases/latest) |
| Linux (Flatpak) | `flatpak install io.github.Loganavter.Improve-ImgSLI`, затем `flatpak run io.github.Loganavter.Improve-ImgSLI` |
| Linux (AUR) | `yay -S improve-imgsli` |
| Из исходников | `git clone … && cd Improve-ImgSLI && ./launcher.sh run` |

Полные инструкции: [docs/INSTALL.md](docs/INSTALL.md) · лаунчер: [docs/LAUNCHER.md](docs/LAUNCHER.md).

Текущее ограничение: изображения больше `65536 px` по стороне отклоняются на
ограниченном пути декодирования (потоковое декодирование такого лимита не имеет);
экспорт изображения больше `16384 px` по стороне работает, но предупреждает, что
путь не тестировался.

## Первые пять минут

1. Запустите приложение — откроется выбор сессии; выберите **Image Compare**,
   **Multi Compare** или **Image Gallery** (каждый выбор открывается своей вкладкой).
2. Нажмите <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> — **Find Action** находит
   любую команду по имени; «Learn more» открывает соответствующую страницу справки.
3. В Image Compare добавьте изображения (кнопка или drag-and-drop), затем двигайте
   линию сплита и зумите колесом; <kbd>Space</kbd> + ЛКМ/ПКМ — предпросмотр стороны.
4. Включите лупу, выберите интерполяцию, настройте зум; экспортируйте собранный вид.
5. В галерее проанализируйте папку: метрики по каждой паре и AI-оценка, если настроен ключ API.

Горячие клавиши, настройки и полный сценарий — во встроенной **справке** (меню Help);
исходники: [EN host topics](src/resources/help/en/) · [RU](src/resources/help/ru/) ·
[Image Compare](src/tabs/image_compare/resources/help/ru/) ·
[Multi Compare](src/tabs/multi_compare/resources/help/ru/) ·
[Gallery](src/tabs/image_gallery/resources/help/ru/).

## Карта документации

| Что нужно | Где читать |
|---|---|
| Установка / лаунчер | [docs/INSTALL.md](docs/INSTALL.md), [docs/LAUNCHER.md](docs/LAUNCHER.md) |
| Вести приложение агентом | [docs/dev/MCP.md](docs/dev/MCP.md) |
| Участие в разработке | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Архитектура, контракты, паттерны | [docs/dev/ARCHITECTURE.md](docs/dev/ARCHITECTURE.md), [docs/dev/CONTRACTS.md](docs/dev/CONTRACTS.md) |
| Видение и история проекта | [VISION.md](VISION.md), [docs/DEVELOPMENT_HISTORY.md](docs/DEVELOPMENT_HISTORY.md) |
| Открытый технический долг | [docs/dev/TODO.md](docs/dev/TODO.md) |

## Участие

Мы рады вкладу — см. [CONTRIBUTING.md](CONTRIBUTING.md): настройка окружения,
правила кода и упаковка. Issues и PR — на GitHub.

## Мейнтейнеры

<table>
  <tr>
    <td align="center" align="top" width="140">
      <a href="https://github.com/nebulosa2007" title="GitHub profile">
        <img src="https://github.com/nebulosa2007.png?size=100" alt="Nebulosa's Avatar" width="100" style="border-radius: 50%;"><br/>
        <sub><b>Nebulosa</b></sub>
      </a>
    </td>
    <td valign="top">
      <strong>Мейнтейнер пакета AUR</strong>
      <p>Большое спасибо Nebulosa за поддержку <a href="https://aur.archlinux.org/packages/improve-imgsli">пакета Arch Linux (AUR)</a> с самого начала — исправления упаковки и работа над стабильностью, которые держат проект надёжным в экосистеме Arch.</p>
      <a href="https://github.com/nebulosa2007"><img src="https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub"></a>
      <a href="https://aur.archlinux.org/account/Nebulosa"><img src="https://img.shields.io/badge/AUR-1793D1?style=for-the-badge&logo=arch-linux&logoColor=white" alt="AUR Profile"></a>
    </td>
  </tr>
</table>

## Лицензия

GPL-3.0-or-later — см. [LICENSE](LICENSE). Зависимости времени выполнения
(включая PySide6/Qt под LGPL-3.0-or-later) перечислены в [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

## История звёзд

![Star History Chart](https://api.star-history.com/svg?repos=Loganavter/Improve-ImgSLI&type=Timeline)
