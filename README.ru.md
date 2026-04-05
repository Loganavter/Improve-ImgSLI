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

<p align="center"><strong>Интуитивный инструмент с открытым исходным кодом для продвинутого сравнения изображений.</strong></p>

<p align="center">
  Читать на других языках:
  <a href="readme.md">English</a>
</p>

---

## 📸 Предпросмотр

<div align="center">
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/1.5/Improve_ImgSLI/screenshots/screenshot_1.png" width="75%">
</div>

<details>
  <summary>Пример полноразрешённого сохранения</summary>
  <img src="https://raw.githubusercontent.com/Loganavter/media_archive/1.4/Improve_ImgSLI/fullres/github_fullres.png" alt="Full resolution example" width="33%">
</details>

---

## 🧭 Быстрые ссылки

- Скачать: <a href="https://github.com/Loganavter/Improve-ImgSLI/releases/latest">Windows installer</a> • <a href="https://flathub.org/apps/details/io.github.Loganavter.Improve-ImgSLI">Flathub</a> • <a href="https://aur.archlinux.org/packages/improve-imgsli">AUR</a>
- Установка и запуск из исходников: <a href="docs/INSTALL.md">docs/INSTALL.md</a>
- Изучить приложение (Справка): <a href="src/resources/help/ru/introduction.md">RU Введение</a> • <a href="src/resources/help/ru/">RU Все разделы</a> • <a href="src/resources/help/en/">EN Docs</a>
- Внести вклад: <a href="CONTRIBUTING.md">CONTRIBUTING.md</a>
- Ещё: <a href="HISTORY.md">История разработки</a> • <a href="VISION.md">Взгляд автора</a>

---

## 🚀 Ключевые возможности

- 🔬 Анализ, а не просто слайдер: интерактивные режимы Highlight, Grayscale, Edge Comparison и SSIM Map, плюс опциональные метрики PSNR/SSIM для объективной проверки отличий.
- 📤 WYSIWYG-экспорт для реальных сравнений: сохранение ровно того композита, который вы видите на экране, включая сплиттеры, лупу, оверлеи и стилизованные названия файлов, в PNG, JPEG, WEBP, BMP, TIFF и JXL.
- 🎬 Запись сессий, таймлайн и экспорт видео: запись процесса сравнения, обрезка или удаление диапазонов на таймлайне, анимация состояний сравнения через keyframes и экспорт в MP4, WebM, AVI, GIF, ProRes, AV1 и другие форматы.
- 🔍 Высокоточная лупа: двойной или объединённый круг, внутренний сплит, субпиксельная стабильность, поддержка EWA Lanczos, freeze-режим, «лазерные» направляющие и точное управление через WASD/QE.
- 🖼️ Быстрое интерактивное сравнение: вертикальный/горизонтальный сплит, синхронные pan/zoom, режимы просмотра каналов и мгновенный предпросмотр одного изображения через Space + кнопки мыши.
- 🗂️ Файловый workflow без лишних движений: drag-and-drop, переупорядочивание между левым/правым списками, вставка из буфера, рейтинги, редактирование имён и быстрое переключение изображений колёсиком мыши.
- 🎨 Глубокая настройка интерфейса: видимость, цвет и толщина разделителей, стилизация лупы, настройка текстовых оверлеев, кастомные кнопки-иконки, светлая/тёмная темы и собственный UI-шрифт.
- ⚙️ Нормальный desktop UX: сохранение компоновки и настроек, мультиязычный интерфейс (EN/RU/zh/pt_BR), трей, уведомления после сохранения, опции автообрезки и удобный launcher для запуска из исходников.

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
Полные инструкции: <a href="docs/INSTALL.md">docs/INSTALL.md</a>.

---

## 🧪 Быстрый старт (Basic Usage)

1. Запустите Improve-ImgSLI.
2. Загрузите изображения через «Add Img(s)» или перетаскиванием. Для быстрого просмотра одного изображения используйте Space + ЛКМ/ПКМ.
3. Передвигайте линию разделения мышью, при необходимости включите горизонтальный сплит.
4. Включите лупу, выберите интерполяцию, настройте масштаб/позицию слайдерами или клавишами.
5. Настройте разделители и текст, затем экспортируйте итоговое изображение.

Для подробных руководств, горячих клавиш и настроек используйте встроенную справку («?») или откройте:
- RU: <a href="src/resources/help/ru/introduction.md">Введение</a> • <a href="src/resources/help/ru/">Все разделы</a>
- EN: <a href="src/resources/help/en/introduction.md">Introduction</a> • <a href="src/resources/help/en/">All topics</a>

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

MIT License. См. <a href="LICENSE">LICENSE</a>.

---

## ⭐ История звёзд

![Star History Chart](https://api.star-history.com/svg?repos=Loganavter/Improve-ImgSLI&type=Timeline)
