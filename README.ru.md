<p align="center">
  <img src="https://raw.githubusercontent.com/johnpetersa19/Improve-ImgSLI/037ab021aa79aa40a85a25d591e887dca85cd50d/src/icons/logo-github%20.svg" alt="Logo" width="384">
</p>

<p align="center">
  <a href="https://github.com/Loganavter/Improve-ImgSLI/releases/latest">
    <img src="https://img.shields.io/github/v/release/Loganavter/Improve-ImgSLI?style=flat-square">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/github/license/Loganavter/Improve-ImgSLI?style=flat-square">
  </a>
  <a href="https://github.com/Loganavter/Improve-ImgSLI/releases">
    <img src="https://img.shields.io/github/downloads/Loganavter/Improve-ImgSLI/total?style=flat-square" alt="GitHub Downloads">
  </a>
  <a href="https://flathub.org/apps/details/io.github.Loganavter.Improve-ImgSLI">
    <img src="https://img.shields.io/flathub/downloads/io.github.Loganavter.Improve-ImgSLI?style=flat-square" alt="Flathub Downloads">
  </a>
</p>

<p align="center"><strong>Платформа с открытым исходным кодом для продвинутого сравнения изображений и медиа.</strong></p>

<p align="center">
  Читать на других языках:
  <a href="readme.md">English</a>
</p>

---

## 📸 Предпросмотр

<div align="center">
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/2.0.0/Improve_ImgSLI/screenshots/screenshot_1.jpg" width="75%">
</div>

---

## 🧭 Быстрые ссылки

- Скачать: <a href="https://github.com/Loganavter/Improve-ImgSLI/releases/latest">Windows installer</a> • <a href="https://flathub.org/apps/details/io.github.Loganavter.Improve-ImgSLI">Flathub</a> • <a href="https://aur.archlinux.org/packages/improve-imgsli">AUR</a>
- Установка и запуск из исходников: <a href="docs/INSTALL.md">docs/INSTALL.md</a> • справка по launcher: <a href="docs/LAUNCHER.md">docs/LAUNCHER.md</a>
- Изучить приложение: встроенный <strong>поиск действий</strong> (<code>Ctrl+Shift+P</code>) и Справка • темы: <a href="src/resources/help/ru/platform/getting_started.md">RU Начало работы</a> • <a href="src/resources/help/ru/">RU</a> • <a href="src/resources/help/en/">EN</a>
- Внести вклад: <a href="CONTRIBUTING.md">CONTRIBUTING.md</a>
- Ещё: <a href="docs/DEVELOPMENT_HISTORY.md">История разработки</a> • <a href="VISION.md">Взгляд автора</a>

---

## 🚀 Ключевые возможности

- 🗂️ Платформа с вкладками: приложение открывается на экране выбора сессии, где можно создать несколько независимых вкладок — пока доступны двухстороннее **Сравнение изображений** и синхронизированное **Мультисравнение** на N картинок; переключение через полоску вкладок в духе Firefox, у каждой вкладки своё состояние, холст и пайплайн экспорта; в планах — новые типы сессий.
- 🔬 Анализ, а не просто слайдер: интерактивные режимы подсветки различий, градаций серого, сравнения краёв и карты SSIM, плюс опциональные метрики PSNR/SSIM.
- 📤 WYSIWYG-экспорт: сохранение ровно того композита, что на экране — разделители, лупа, оверлеи и оформленные имена файлов — в PNG, JPEG, WEBP, BMP, TIFF и JXL.
- 🎬 Запись сессий, таймлайн и экспорт видео: запись процесса сравнения, обрезка или удаление диапазонов, анимация состояний и экспорт в MP4, WebM, AVI, GIF, ProRes, AV1 и другие форматы.
- 🔍 Высокоточная лупа: двойной или объединённый круг, внутренний сплит, субпиксельная стабильность, поддержка EWA Lanczos, режим заморозки, «лазерные» направляющие и точное управление WASD/QE.
- 🔭 Несколько луп на одном сравнении: у каждой свои зона захвата, положение, размер, цвета и заморозка; можно скрывать, восстанавливать и удалять по отдельности, есть автоцвет для новых экземпляров и живая подсветка пересечения зон при перетаскивании.
- 🖼️ Быстрый интерактивный холст: вертикальный/горизонтальный раздел, плавные GPU-зум и панорама, синхронный зум/пан для обеих сторон, режимы каналов, сглаженные разделители и оверлеи, мгновенный просмотр одной стороны через Space + кнопки мыши.
- 🔀 Вкладка **Мультисравнение**: любое число изображений в одной сцене, перетаскивание слотов для перестройки раскладки, свободное изменение разделителей и полноэкранный режим фокуса по двойному клику на ячейку.
- 🗂️ Удобная работа с файлами: перетаскивание, переупорядочивание между списками сторон, вставка из буфера, рейтинги, правка имён и быстрое переключение колёсиком мыши.
- 🎨 Глубокая настройка интерфейса: видимость, цвет и толщина разделителей, стилизация лупы и текстовых подписей, кнопки-иконки, светлая/тёмная темы и свой UI-шрифт — на базе собственного UI-тулкита проекта.
- 🔎 Поиск действий и иллюстрированная справка: `Ctrl+Shift+P` ищет и запускает любую команду («Подробнее» открывает нужную тему); иерархическая справка с хабами, карточками и страницами для сессий **Сравнение изображений** / **Мультисравнение**.
- ⚙️ Нормальный desktop-опыт: сохранение компоновки и настроек, мультиязычный интерфейс (EN/RU/zh/pt_BR), трей, уведомления после сохранения, автообрезка и удобный launcher для запуска из исходников.

---

## 🛠 Установка

Для пользователей:
- Windows: скачайте и запустите инсталлятор из <a href="https://github.com/Loganavter/Improve-ImgSLI/releases/latest">Releases</a>.
- Linux (Flatpak): <code>flatpak install io.github.Loganavter.Improve-ImgSLI</code>, затем <code>flatpak run io.github.Loganavter.Improve-ImgSLI</code>.
- Linux (AUR): <code>yay -S improve-imgsli</code>.

Из исходников (минимально):
```bash
git clone https://github.com/Loganavter/Improve-ImgSLI.git
cd Improve-ImgSLI
chmod +x launcher.sh
./launcher.sh run
```
Полные инструкции: <a href="docs/INSTALL.md">docs/INSTALL.md</a>; команды launcher: <a href="docs/LAUNCHER.md">docs/LAUNCHER.md</a>.

Текущее ограничение:
- Изображения больше `65536 px` по любой стороне отклоняются при загрузке: это защита от патологического decode (кадр всё ещё разжимается целиком один раз; spill в `TiledPixelStore` пишется полосами без второго полного буфера), а не потолок тайлинга. Экспорт кадра больше `16384 px` по стороне разрешён, но показывается предупреждение, что путь не тестировали.

---

## 🧪 Быстрый старт

1. Запустите Improve-ImgSLI — откроется экран выбора сессии; выберите **Сравнение изображений** для классического сравнения двух картинок или **Мультисравнение**, чтобы выложить сразу несколько. Каждый выбор открывается в своей вкладке.
2. В любой момент нажмите `Ctrl+Shift+P` — **поиск действий**: настройки, инструменты и действия сессии по имени; «Подробнее» на строке открывает соответствующую тему справки.
3. В сессии **Сравнение изображений** загрузите файлы через «Доб. Изобр(ы)» или перетаскиванием. Для быстрого просмотра одной стороны используйте `Space + ЛКМ/ПКМ`.
4. Передвигайте линию разделения мышью, при необходимости включите горизонтальный раздел.
5. Включите лупу, выберите интерполяцию, настройте масштаб и позицию слайдерами или клавишами.
6. В объединённой лупе можно принудительно выбрать сторону через `Space + Shift + ЛКМ/ПКМ`.
7. Настройте разделители и текст, затем экспортируйте итоговое изображение.
8. В **Мультисравнении** добавляйте изображения перетаскиванием или с панели инструментов, перетаскивайте слоты для перестройки раскладки, меняйте размеры разделителей и открывайте полноэкранный режим фокуса двойным кликом по ячейке.

Для подробных руководств, горячих клавиш и настроек используйте встроенную справку (меню «Справка» или поиск действий → Справка) или исходники:
- RU: <a href="src/resources/help/ru/platform/getting_started.md">Начало работы</a> • <a href="src/resources/help/ru/">Темы приложения</a> • <a href="src/tabs/image_compare/resources/help/ru/">Сравнение изображений</a> • <a href="src/tabs/multi_compare/resources/help/ru/">Мультисравнение</a>
- EN: <a href="src/resources/help/en/platform/getting_started.md">Getting Started</a> • <a href="src/resources/help/en/">Host topics</a>

---

## 🤝 Вклад

Спасибо за ваш интерес к проекту! Пожалуйста, ознакомьтесь с <a href="CONTRIBUTING.md">CONTRIBUTING.md</a> для настройки окружения разработки и правил оформления PR. Сообщайте о проблемах и предлагайте изменения через Issues/PRs на GitHub.

---

## 🫂 Мейнтейнеры

Проект развивается благодаря усилиям мейнтейнеров. Отдельная благодарность:

<table>
  <tr>
    <td align="center" valign="top" width="140">
      <a href="https://github.com/nebulosa2007" title="GitHub profile">
        <img src="https://github.com/nebulosa2007.png?size=100" alt="Nebulosa's Avatar" width="100" style="border-radius: 50%;"><br/>
        <sub><b>Nebulosa</b></sub>
      </a>
    </td>
    <td valign="top">
      <strong>AUR Package Maintainer</strong>
      <p>Огромная благодарность Nebulosa за поддержание пакета <a href="https://aur.archlinux.org/packages/improve-imgsli">Arch Linux (AUR)</a> с самого начала, оперативные фиксы и стабильность для сообщества Arch.</p>
      <a href="https://github.com/nebulosa2007"><img src="https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub"></a>
      <a href="https://aur.archlinux.org/account/Nebulosa"><img src="https://img.shields.io/badge/AUR-1793D1?style=for-the-badge&logo=arch-linux&logoColor=white" alt="AUR Profile"></a>
    </td>
  </tr>
</table>

---

## 📄 Лицензия

GPL-3.0-or-later. См. <a href="LICENSE">LICENSE</a>.

Зависимости времени выполнения (включая PySide6/Qt под LGPL-3.0-or-later) — в <a href="THIRD_PARTY_LICENSES.md">THIRD_PARTY_LICENSES.md</a>.

---

## ⭐ История звёзд

![Star History Chart](https://api.star-history.com/svg?repos=Loganavter/Improve-ImgSLI&type=Timeline)
