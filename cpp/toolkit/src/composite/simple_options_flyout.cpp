#include "sli/toolkit/composite/simple_options_flyout.h"

#include <chrono>
#include <optional>

#include <QApplication>
#include <QEasingCurve>
#include <QEnterEvent>
#include <QFontMetrics>
#include <QFrame>
#include <QGuiApplication>
#include <QHBoxLayout>
#include <QHideEvent>
#include <QKeyEvent>
#include <QLabel>
#include <QMouseEvent>
#include <QPainter>
#include <QPaintEvent>
#include <QPen>
#include <QPropertyAnimation>
#include <QScrollArea>
#include <QScreen>
#include <QVBoxLayout>
#include <QWidget>

#include "sli/toolkit/atomic/minimalist_scrollbar.h"
#include "sli/toolkit/composite/flyout.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit {

// ─── SimpleRow ───────────────────────────────────────────────────────────────
// Internal row widget mirroring Python's _SimpleRow.
// Custom paintEvent handles _RowBackgroundLayer and _CurrentIndicatorLayer.

namespace {

class SimpleRow final : public QWidget {
  Q_OBJECT

 public:
  explicit SimpleRow(int index,
                     const QString& text,
                     bool isCurrent,
                     int itemHeight,
                     const QFont& itemFont,
                     QWidget* parent = nullptr)
      : QWidget(parent), index_(index), text_(text), isCurrent_(isCurrent) {
    setFixedHeight(itemHeight);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    setCursor(Qt::PointingHandCursor);
    setMouseTracking(true);

    auto* layout = new QHBoxLayout(this);
    layout->setContentsMargins(10, 0, 10, 0);

    label_ = new QLabel(text, this);
    label_->setFont(itemFont);
    label_->setAttribute(Qt::WA_TransparentForMouseEvents, true);
    applyLabelStyle();
    layout->addWidget(label_);

    Theme::onThemeChanged(this, [this]() {
      applyLabelStyle();
      update();
    });
  }

  int rowIndex() const { return index_; }
  bool isCurrent() const { return isCurrent_; }
  void setIsCurrent(bool c) {
    if (isCurrent_ != c) {
      isCurrent_ = c;
      update();
    }
  }

 signals:
  void rowClicked(int index);

 protected:
  void paintEvent(QPaintEvent*) override {
    // _RowBackgroundLayer: inset rounded rect, list_item.background tokens
    const bool active = isCurrent_ || isHovered_;
    const QString key = active ? QStringLiteral("list_item.background.hover")
                               : QStringLiteral("list_item.background.normal");
    const QColor bgColor = Theme::getColor(key);

    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);

    // Inset by 2 on each side (.adjusted(2, 2, -2, -2))
    const QRect bgRect = rect().adjusted(2, 2, -2, -2);
    p.setPen(Qt::NoPen);
    p.setBrush(bgColor);
    p.drawRoundedRect(bgRect, 5, 5);

    // _CurrentIndicatorLayer: left accent line, only when is_current
    if (isCurrent_) {
      const QColor accentColor = Theme::getColor(QStringLiteral("accent"));
      QPen pen(accentColor);
      pen.setWidth(3);
      pen.setCapStyle(Qt::RoundCap);
      p.setPen(pen);
      const int x = rect().left() + pen.width();
      p.drawLine(x, rect().top() + 7, x, rect().bottom() - 7);
    }
  }

  void enterEvent(QEnterEvent* event) override {
    isHovered_ = true;
    update();
    QWidget::enterEvent(event);
  }

  void leaveEvent(QEvent* event) override {
    isHovered_ = false;
    update();
    QWidget::leaveEvent(event);
  }

  void mousePressEvent(QMouseEvent* event) override {
    if (event->button() == Qt::LeftButton) {
      isPressed_ = true;
      update();
    }
    QWidget::mousePressEvent(event);
  }

  void mouseReleaseEvent(QMouseEvent* event) override {
    if (event->button() == Qt::LeftButton && isPressed_) {
      isPressed_ = false;
      update();
      if (rect().contains(event->pos())) {
        emit rowClicked(index_);
      }
    }
    QWidget::mouseReleaseEvent(event);
  }

 private:
  void applyLabelStyle() {
    // Mirrors Python's _apply_label_style: font not bold, class "option-label"
    QFont f = label_->font();
    f.setBold(false);
    label_->setFont(f);
    label_->setProperty("class", QStringLiteral("option-label"));
    // Use dialog.text token for label color (standard text color in flyouts)
    const QColor textColor = Theme::getColor(QStringLiteral("dialog.text"));
    label_->setStyleSheet(
        QStringLiteral("color: %1; background: transparent;")
            .arg(textColor.name(QColor::HexArgb)));
  }

  int index_ = 0;
  QString text_;
  bool isCurrent_ = false;
  bool isHovered_ = false;
  bool isPressed_ = false;
  QLabel* label_ = nullptr;
};

}  // namespace

// We need the MOC to process SimpleRow defined inside an anonymous namespace
// inside a .cpp. Use #include at the bottom.

// ─── SimpleOptionsFlyout ──────────────────────────────────────────────────────

SimpleOptionsFlyout::SimpleOptionsFlyout(QWidget* parentWidget)
    : Flyout(parentWidget), parentWidget_(parentWidget) {

  setObjectName(QStringLiteral("sliSimpleOptionsFlyout"));

  // Python: self._item_font = QFont(QApplication.font(self))
  itemFont_ = QApplication::font(this);

  // Python: self.content_layout.setSpacing(0)
  //         self.content_layout.setContentsMargins(4, 4, 4, 4)
  contentLayout_->setSpacing(0);
  contentLayout_->setContentsMargins(4, 4, 4, 4);

  // Scroll area — mirrors Python setup
  scrollArea_ = new QScrollArea(this);
  scrollArea_->setWidgetResizable(true);
  scrollArea_->setFrameShape(QFrame::NoFrame);
  scrollArea_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
  scrollArea_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
  scrollArea_->setVerticalScrollBar(new MinimalistScrollBar(Qt::Vertical));
  scrollArea_->setStyleSheet(
      QStringLiteral("QScrollArea { background: transparent; border: none; }"));
  scrollArea_->viewport()->setAutoFillBackground(false);
  scrollArea_->viewport()->setStyleSheet(
      QStringLiteral("background: transparent;"));

  // Rows container
  rowsContainer_ = new QWidget();
  rowsContainer_->setStyleSheet(QStringLiteral("background: transparent;"));
  rowsLayout_ = new QVBoxLayout(rowsContainer_);
  rowsLayout_->setContentsMargins(0, 0, 0, 0);
  rowsLayout_->setSpacing(2);
  rowsLayout_->addStretch();

  scrollArea_->setWidget(rowsContainer_);
  contentLayout_->addWidget(scrollArea_);

  hide();
}

void SimpleOptionsFlyout::setMaxVisibleItems(int n) {
  maxVisibleItems_ = std::max(1, n);
}

void SimpleOptionsFlyout::setRowHeight(int h) {
  itemHeight_ = std::max(28, h);
}

void SimpleOptionsFlyout::setRowFont(const QFont& f) {
  itemFont_ = f;
}

void SimpleOptionsFlyout::populate(const QStringList& labels, int currentIndex) {
  options_ = labels;
  currentIndex_ =
      (currentIndex >= 0 && currentIndex < options_.size()) ? currentIndex : -1;

  // Batch update — mirrors Python setUpdatesEnabled(False) around clear+build
  rowsContainer_->setUpdatesEnabled(false);

  // Clear existing rows (keep trailing stretch — it's always the last item)
  while (rowsLayout_->count() > 1) {
    QLayoutItem* item = rowsLayout_->takeAt(0);
    if (QWidget* w = item ? item->widget() : nullptr) {
      w->deleteLater();
    }
    delete item;
  }
  rowWidgets_.clear();

  for (int i = 0; i < options_.size(); ++i) {
    QWidget* row = createRow(i, options_[i], i == currentIndex_, itemHeight_, itemFont_);
    rowWidgets_.push_back(row);
    // Insert before the trailing stretch (always at rowsLayout_->count()-1)
    rowsLayout_->insertWidget(rowsLayout_->count() - 1, row);
  }

  updateSize();
  rowsContainer_->setUpdatesEnabled(true);
}

QWidget* SimpleOptionsFlyout::createRow(int index, const QString& text,
                                        bool isCurrent, int itemHeight,
                                        const QFont& itemFont) {
  auto* row = new SimpleRow(index, text, isCurrent, itemHeight, itemFont,
                            rowsContainer_);
  connect(row, &SimpleRow::rowClicked, this,
          &SimpleOptionsFlyout::onRowClicked);
  return row;
}

void SimpleOptionsFlyout::updateSize(int matchWidth, bool exactMatch,
                                     std::optional<int> availableHeight) {
  const int num = options_.size();
  const int spacing = rowsLayout_->spacing();  // 2
  const QMargins outerMargins = contentLayout_->contentsMargins();
  const int marginsV = outerMargins.top() + outerMargins.bottom();

  int contentH = 0;
  int visible = 0;
  if (num == 0) {
    visible = 1;
    contentH = 50;
  } else {
    visible = std::min(num, maxVisibleItems_);
    if (availableHeight.has_value()) {
      // budget = available_height - 2 * MARGIN - margins_v
      const int budget = *availableHeight - 2 * kMargin - marginsV;
      if (budget > 0) {
        const int maxByHeight =
            std::max(1, (budget + spacing) / (itemHeight_ + spacing));
        visible = std::min(visible, maxByHeight);
      }
    }
    contentH = visible * itemHeight_ + std::max(0, visible - 1) * spacing;
  }

  const int containerH = contentH + marginsV;

  QFontMetrics fm(itemFont_);
  int maxTextWidth = 0;
  for (const auto& text : options_) {
    maxTextWidth = std::max(maxTextWidth, fm.horizontalAdvance(text));
  }

  const int finalW = maxTextWidth + 50;

  int width = 0;
  if (exactMatch && matchWidth > 0) {
    const int targetContainerWidth = std::max(1, matchWidth - kMargin * 2);
    width = std::max(finalW, targetContainerWidth);
  } else if (matchWidth > 0) {
    const int targetContainerWidth = matchWidth - kMargin * 2;
    const int minContainerWidth = std::max(180, targetContainerWidth);
    width = std::max(finalW, minContainerWidth);
  } else {
    width = std::max(finalW, 180);
  }

  // Python: self.container.setFixedSize(width, container_h)
  //         total_width = width + MARGIN * 2
  //         self.setFixedSize(total_width, container_h + MARGIN * 2)
  // In the C++ port we use Flyout (no separate container_ member visible here),
  // so we set the flyout's own fixed size to include margins.
  const int totalWidth = width + kMargin * 2;
  const int totalHeight = containerH + kMargin * 2;
  setFixedSize(totalWidth, totalHeight);
}

void SimpleOptionsFlyout::showBelow(QWidget* anchorWidget, bool exactWidthMatch) {
  if (isVisible() && anchorWidget_ == anchorWidget) {
    justOpened_ = false;
    hide();
    return;
  }

  anchorWidget_ = anchorWidget;

  if (anim_) {
    anim_->stop();
    anim_ = nullptr;
  }

  // Determine anchor width
  int anchorWidth = anchorWidget->frameGeometry().width();
  if (anchorWidth <= 0) {
    anchorWidth = anchorWidget->geometry().width();
  }
  if (anchorWidth <= 0) {
    anchorWidth = anchorWidget->width();
  }

  justOpened_ = true;
  openTimestamp_ = std::chrono::steady_clock::now();

  const int offset = kAppearExtraY - kMargin;
  const int gap = kWindowMargin;

  // Resolve host window and available rect
  QWidget* host = anchorWidget->window();
  if (parentWidget() != host) {
    setParent(host);
  }

  const QRect anchorRect(anchorWidget->mapTo(host, QPoint(0, 0)),
                         anchorWidget->size());
  const QRect avail = host->rect();

  const int spaceBelow =
      avail.bottom() - anchorRect.bottom() - offset - gap;
  const int spaceAbove =
      anchorRect.top() - avail.top() - offset - gap;
  const int budget = std::max(spaceBelow, spaceAbove);

  updateSize(anchorWidth, exactWidthMatch, budget);

  const int totalWidth = this->width();
  const int totalHeight = this->height();

  // Determine vertical position
  int finalY = 0;
  if (spaceBelow >= totalHeight || spaceBelow >= spaceAbove) {
    finalY = anchorRect.bottom() + offset;
  } else {
    finalY = anchorRect.top() - offset - totalHeight;
  }

  // Center horizontally on anchor
  const int anchorCenterX =
      anchorWidget->mapTo(host, anchorWidget->rect().center()).x();
  int finalX = static_cast<int>(anchorCenterX - totalWidth / 2.0) + 2;

  // Clamp to available rect
  finalX = std::max(avail.left(),
                    std::min(finalX, avail.right() - totalWidth));
  finalY = std::max(avail.top(),
                    std::min(finalY, avail.bottom() - totalHeight));

  const QPoint startPos(finalX, finalY - dropOffsetPx_);
  const QPoint endPos(finalX, finalY);

  move(startPos);
  setVisible(true);
  raise();
  setFocus(Qt::PopupFocusReason);

  QApplication::processEvents();

  // Enforce exact width after processEvents (mirrors Python warning + fix)
  if (exactWidthMatch && this->width() != totalWidth) {
    setFixedSize(totalWidth, totalHeight);
  }

  // Drop-in animation
  auto* animPos = new QPropertyAnimation(this, "pos", this);
  animPos->setDuration(moveDurationMs_);
  animPos->setStartValue(startPos);
  animPos->setEndValue(endPos);
  animPos->setEasingCurve(QEasingCurve::OutQuad);
  connect(animPos, &QPropertyAnimation::finished, this,
          &SimpleOptionsFlyout::onAnimationFinished);
  anim_ = animPos;
  animPos->start();
}

void SimpleOptionsFlyout::onAnimationFinished() {
  if (anim_) {
    QPropertyAnimation* a = anim_;
    anim_ = nullptr;
    a->deleteLater();
  }
}

void SimpleOptionsFlyout::onRowClicked(int idx) {
  emit itemChosen(idx);
  justOpened_ = false;
  hide();
}

void SimpleOptionsFlyout::hide() {
  Flyout::hide();
  // Python: restore focus to parent window
  if (parentWidget_) {
    if (QWidget* win = parentWidget_->window()) {
      win->activateWindow();
      win->setFocus();
    }
  }
}

void SimpleOptionsFlyout::hideEvent(QHideEvent* event) {
  // Python hideEvent: guard against closing too soon after open
  if (justOpened_) {
    using Seconds = std::chrono::duration<double>;
    const double timeSinceOpen =
        std::chrono::duration_cast<Seconds>(
            std::chrono::steady_clock::now() - openTimestamp_)
            .count();
    if (timeSinceOpen < 0.3) {
      event->ignore();
      return;
    }
    justOpened_ = false;
  }

  Flyout::hideEvent(event);

  if (anim_) {
    anim_->stop();
    anim_ = nullptr;
  }

  justOpened_ = false;

  emit closed();
}

void SimpleOptionsFlyout::ensureOverlayParent(QWidget* anchor) {
  QWidget* host = anchor ? anchor->window() : nullptr;
  if (host && parentWidget() != host) {
    setParent(host);
  }
}

}  // namespace sli::toolkit

// Required: MOC for SimpleRow defined in anonymous namespace in this .cpp
#include "simple_options_flyout.moc"
