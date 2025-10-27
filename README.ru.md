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

- 🖼️ Сравнение и просмотр: вертикальный/горизонтальный сплит, синхронная навигация, быстрый предпросмотр (Space + кнопки мыши).
- 🔍 Лупа: двойной или разделённый круг, интерполяции (Nearest/Bilinear/Bicubic/Lanczos), точное управление WASD/QE, фиксация позиции.
- 🗂️ Потоки и файлы: drag-n-drop, переупорядочивание между левым/правым списками, короткое/долгое нажатие, рейтинги, редактирование имён, вставка из буфера (Ctrl+V).
- 🎨 Оверлеи и UI: Полностью кастомный интерфейс с настраиваемыми разделителями сравнения и лупы (видимость, цвет, толщина), кастомными иконками, светлой/тёмной темами и пользовательским шрифтом UI.
- 📤 Экспорт: WYSIWYG экспорт текущего композита (сплиттер, лупа, текст), форматы PNG/JPEG/WEBP/BMP/TIFF, управление качеством, стили текста.
- ⚙️ UX и настройки: сохранение состояния окна/компоновки, мультиязычный интерфейс (EN/RU/zh/pt_BR), скрипт-лаунчер для venv, отладки и профилирования.

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