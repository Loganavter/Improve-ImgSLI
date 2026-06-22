#include "sli/toolkit/composite/sidebar_nav_list.h"

#include <QEnterEvent>
#include <QFrame>
#include <QImage>
#include <QMouseEvent>
#include <QPainter>
#include <QPaintEvent>
#include <QScrollBar>
#include <QSizePolicy>
#include <QVBoxLayout>

#include "sli/toolkit/composite/unified_flyout/minimalist_scrollbar.h"
#include "sli/toolkit/helpers/icon_pixmap.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit {

// =====================================================================
// NavRowButton
// =====================================================================

NavRowButton::NavRowButton(const QString& text,
                           int rowHeight,
                           int iconSize,
                           QWidget* parent)
    : QWidget(parent),
      text_(text),
      iconSizePx_(iconSize > 0 ? iconSize : 24) {
  setObjectName(QStringLiteral("sliNavRowButton"));
  setFixedHeight(rowHeight > 0 ? rowHeight : 44);
  setMinimumWidth(0);
  setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
  setFocusPolicy(Qt::NoFocus);
  setMouseTracking(true);
  setToolTip(text);
}

void NavRowButton::setSelected(bool selected) {
  if (selected_ == selected) return;
  selected_ = selected;
  updateBg();
  update();
}

void NavRowButton::setNavPixmaps(const QPixmap& normal,
                                  const QPixmap& selected) {
  normalPixmap_ = normal;
  selectedPixmap_ = selected;
  update();
}

void NavRowButton::setText(const QString& text) {
  text_ = text;
  setToolTip(text);
  update();
}

void NavRowButton::updateBg() {
  // Background update is handled in paintEvent from current state
  update();
}

void NavRowButton::paintEvent(QPaintEvent*) {
  QPainter p(this);
  p.setRenderHint(QPainter::Antialiasing);

  const auto& colors = Theme::palette();

  // Resolve background color (mirrors _sidebar_nav_resolve)
  QColor bg;
  if (!isEnabled()) {
    bg = Theme::getColor(QStringLiteral("list_item.background.normal"));
  } else if (selected_) {
    QColor accent = colors.accent;
    if (accent.isValid())
      bg = accent;
    else
      bg = Theme::getColor(QStringLiteral("list_item.background.hover"));
  } else if (pressed_ || hovered_) {
    bg = Theme::getColor(QStringLiteral("list_item.background.hover"));
  } else {
    bg = Theme::getColor(QStringLiteral("list_item.background.normal"));
  }
  if (!bg.isValid())
    bg = QColor(0, 0, 0, 0);  // transparent

  // Draw rounded rect background
  p.setPen(Qt::NoPen);
  p.setBrush(bg);
  p.drawRoundedRect(rect().adjusted(0, 0, -1, -1), 6, 6);

  // Draw content — icon left + text vertical centre, no horizontal centering
  QPixmap pixmap;
  if (selected_ && !selectedPixmap_.isNull())
    pixmap = selectedPixmap_;
  else
    pixmap = normalPixmap_;

  constexpr int kPad = 12;
  constexpr int kGap = 10;

  int x = kPad;

  if (!pixmap.isNull()) {
    int iconY = (height() - iconSizePx_) / 2;
    p.drawPixmap(x, iconY, pixmap.scaled(iconSizePx_, iconSizePx_,
                                          Qt::KeepAspectRatio,
                                          Qt::SmoothTransformation));
    x += iconSizePx_ + kGap;
  }

  if (!text_.isEmpty()) {
    // Text colour
    QColor textColor = colors.text;
    if (selected_) {
      QColor hlText = Theme::getColor(QStringLiteral("HighlightedText"));
      textColor = hlText.isValid() ? hlText : QColor(Qt::white);
    }
    p.setPen(textColor);

    QRect textRect(x, 0,
                   std::max(0, width() - x - kPad),
                   height());
    QString elided = p.fontMetrics().elidedText(
        text_, Qt::ElideRight, textRect.width());
    p.drawText(textRect,
               Qt::AlignVCenter | Qt::AlignLeft,
               elided);
  }
}

void NavRowButton::enterEvent(QEnterEvent*) {
  hovered_ = true;
  updateBg();
}

void NavRowButton::leaveEvent(QEvent*) {
  hovered_ = false;
  pressed_ = false;
  updateBg();
}

void NavRowButton::mousePressEvent(QMouseEvent* event) {
  if (event->button() == Qt::LeftButton) {
    pressed_ = true;
    updateBg();
  }
  QWidget::mousePressEvent(event);
}

void NavRowButton::mouseReleaseEvent(QMouseEvent* event) {
  if (event->button() == Qt::LeftButton && pressed_) {
    pressed_ = false;
    if (rect().contains(event->pos()))
      emit clicked();
    updateBg();
  }
  QWidget::mouseReleaseEvent(event);
}

// =====================================================================
// IconListWidget
// =====================================================================

IconListWidget::IconListWidget(QWidget* parent,
                               QSize iconSize,
                               int rowHeight,
                               const QString& selectedIconMode)
    : QWidget(parent),
      rowHeight_(rowHeight),
      iconSize_(iconSize.isValid() ? iconSize : QSize(24, 24)),
      selectedIconMode_(normalizeSelectedIconMode(selectedIconMode)) {
  auto* layout = new QVBoxLayout(this);
  layout->setContentsMargins(0, 0, 0, 0);
  layout->setSpacing(0);

  scroll_ = new QScrollArea(this);
  scroll_->setWidgetResizable(true);
  scroll_->setFrameShape(QFrame::NoFrame);
  scroll_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
  scroll_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);

  host_ = new QWidget();
  hostLayout_ = new QVBoxLayout(host_);
  hostLayout_->setContentsMargins(8, 4, 8, 4);
  hostLayout_->setSpacing(8);
  hostLayout_->addStretch(1);
  scroll_->setWidget(host_);
  layout->addWidget(scroll_);

  // Refresh icons on theme change
  Theme::onThemeChanged(this, [this] { refreshIcons(); });
}

IconListWidget::~IconListWidget() = default;

// ----- items -----

void IconListWidget::setItems(const QVector<IconListItem>& items) {
  clear();
  for (const auto& item : items)
    appendRow(item);
}

int IconListWidget::addItem(const QString& text,
                            const QVariant& icon,
                            const QVariant& data,
                            int rowHeight,
                            const QVariant& selectedIcon) {
  IconListItem spec;
  spec.text = text;
  spec.icon = icon;
  spec.data = data;
  spec.rowHeight = (rowHeight > 0) ? rowHeight : rowHeight_;
  spec.selectedIcon = selectedIcon;
  appendRow(spec);
  return rows_.size() - 1;
}

void IconListWidget::clear() {
  for (auto& row : rows_) {
    if (row.button) {
      row.button->setParent(nullptr);
      row.button->deleteLater();
    }
  }
  rows_.clear();
  int prev = currentRow_;
  currentRow_ = -1;
  if (prev != -1) {
    emit currentRowChanged(-1);
    emit currentItemChanged(-1, prev);
  }
}

int IconListWidget::count() const {
  return rows_.size();
}

// ----- selection -----

void IconListWidget::setCurrentRow(int idx) {
  if (idx < 0 || idx >= rows_.size())
    idx = -1;
  if (idx == currentRow_)
    return;

  int prev = currentRow_;
  currentRow_ = idx;

  for (int i = 0; i < rows_.size(); ++i) {
    if (rows_[i].button)
      rows_[i].button->setSelected(i == idx);
  }

  emit currentRowChanged(idx);
  emit currentItemChanged(idx, prev);
}

// ----- item access -----

QString IconListWidget::itemText(int idx) const {
  if (idx < 0 || idx >= rows_.size()) return {};
  return rows_[idx].text;
}

QVariant IconListWidget::itemData(int idx, int role) const {
  if (idx < 0 || idx >= rows_.size()) return {};
  auto it = rows_[idx].dataRoles.find(role);
  return it != rows_[idx].dataRoles.end() ? it.value() : QVariant();
}

void IconListWidget::setItemSizeHint(int idx, const QSize& size) {
  if (idx < 0 || idx >= rows_.size()) return;
  int h = size.height();
  if (h > 0) {
    rows_[idx].rowHeight = h;
    if (rows_[idx].button)
      rows_[idx].button->setFixedHeight(h);
  }
}

void IconListWidget::setItemIcon(int idx, const QVariant& icon) {
  if (idx < 0 || idx >= rows_.size()) return;
  // Support pair notation [normal, selected]
  if (icon.canConvert<QVariantList>()) {
    auto list = icon.toList();
    if (list.size() >= 2) {
      rows_[idx].icon = list[0];
      rows_[idx].selectedIcon = list[1];
    }
  } else {
    rows_[idx].icon = icon;
  }
  applyIcon(rows_[idx]);
}

void IconListWidget::setItemSelectedIcon(int idx, const QVariant& icon) {
  if (idx < 0 || idx >= rows_.size()) return;
  rows_[idx].selectedIcon = icon;
  applyIcon(rows_[idx]);
}

// ----- icon mode -----

void IconListWidget::setIconSize(const QSize& size) {
  if (!size.isValid()) return;
  iconSize_ = size;
  for (auto& row : rows_)
    applyIcon(row);
}

void IconListWidget::refreshIcons() {
  for (auto& row : rows_)
    applyIcon(row);
}

void IconListWidget::setSelectedIconMode(const QString& mode) {
  QString norm = normalizeSelectedIconMode(mode);
  if (norm == selectedIconMode_) return;
  selectedIconMode_ = norm;
  refreshIcons();
}

// ----- scroll appearance -----

void IconListWidget::enableMinimalScrollbar() {
  scroll_->setVerticalScrollBar(new unified_flyout::MinimalistScrollBar());
}

// ----- internals -----

void IconListWidget::appendRow(const IconListItem& spec) {
  QVariant iconVal = spec.icon;
  QVariant selectedIconVal = spec.selectedIcon;

  // Split pair notation in icon
  if (iconVal.canConvert<QVariantList>()) {
    auto list = iconVal.toList();
    if (list.size() >= 2) {
      iconVal = list[0];
      if (!selectedIconVal.isValid())
        selectedIconVal = list[1];
    }
  }

  int rh = spec.rowHeight > 0 ? spec.rowHeight : rowHeight_;
  auto* btn = new NavRowButton(spec.text, rh, iconSize_.height(), this);

  RowSpec row;
  row.text = spec.text;
  row.icon = iconVal;
  row.selectedIcon = selectedIconVal;
  row.rowHeight = rh;
  row.button = btn;
  if (spec.data.isValid())
    row.dataRoles[Qt::UserRole] = spec.data;

  rows_.append(row);
  applyIcon(rows_.last());

  int index = rows_.size() - 1;
  connect(btn, &NavRowButton::clicked, this, [this, index] {
    onRowClicked(index);
  });

  int insertAt = hostLayout_->count() - 1;
  if (insertAt < 0) insertAt = 0;
  hostLayout_->insertWidget(insertAt, btn);
}

void IconListWidget::onRowClicked(int idx) {
  if (idx == currentRow_) return;
  setCurrentRow(idx);
}

void IconListWidget::applyIcon(RowSpec& row) {
  row.normalPixmap = QPixmap();
  row.selectedPixmap = QPixmap();

  auto* btn = row.button;
  if (!btn) return;

  btn->setNavPixmaps(QPixmap(), QPixmap());

  if (!row.icon.isValid()) return;

  int sz = iconSize_.isValid() ? iconSize_.height() : 24;
  QPixmap normalPixmap = normalizedIconPixmap(row.icon, sz);
  if (normalPixmap.isNull()) return;

  row.normalPixmap = normalPixmap;
  row.selectedPixmap = selectedPixmapForRow(row, normalPixmap);
  btn->setNavPixmaps(row.normalPixmap, row.selectedPixmap);
}

QPixmap IconListWidget::selectedPixmapForRow(RowSpec& row,
                                              const QPixmap& normalPixmap) {
  if (selectedIconMode_ == QStringLiteral("replace")) {
    if (!row.selectedIcon.isValid())
      return normalPixmap;
    int sz = iconSize_.isValid() ? iconSize_.height() : 24;
    QPixmap sel = normalizedIconPixmap(row.selectedIcon, sz);
    return sel.isNull() ? normalPixmap : sel;
  }
  // "invert" mode
  QPixmap inv = invertedPixmap(normalPixmap);
  return inv.isNull() ? normalPixmap : inv;
}

QString IconListWidget::normalizeSelectedIconMode(const QString& mode) const {
  QString norm = mode.trimmed().toLower();
  norm.replace(QStringLiteral("-"), QStringLiteral("_"));
  if (norm == QStringLiteral("inversion") || norm == QStringLiteral("inverse"))
    norm = QStringLiteral("invert");
  if (norm == QStringLiteral("replace_icon") || norm == QStringLiteral("replacement"))
    norm = QStringLiteral("replace");

  if (norm != QStringLiteral("invert") && norm != QStringLiteral("replace")) {
    qWarning("selected_icon_mode must be 'invert' or 'replace', got '%s'",
             qPrintable(mode));
    return QStringLiteral("invert");
  }
  return norm;
}

QPixmap IconListWidget::invertedPixmap(const QPixmap& base) const {
  if (base.isNull()) return QPixmap();

  QImage img = base.toImage().convertToFormat(QImage::Format_ARGB32);
  for (int y = 0; y < img.height(); ++y) {
    for (int x = 0; x < img.width(); ++x) {
      QColor c = img.pixelColor(x, y);
      int a = c.alpha();
      if (a == 0) continue;
      c.setRed(255 - c.red());
      c.setGreen(255 - c.green());
      c.setBlue(255 - c.blue());
      c.setAlpha(a);
      img.setPixelColor(x, y, c);
    }
  }
  return QPixmap::fromImage(img);
}

}  // namespace sli::toolkit