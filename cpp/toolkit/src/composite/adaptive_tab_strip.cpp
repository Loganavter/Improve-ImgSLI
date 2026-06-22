#include "sli/toolkit/composite/adaptive_tab_strip.h"

#include <QFontMetrics>
#include <QHBoxLayout>
#include <QLinearGradient>
#include <QMouseEvent>
#include <QPainter>
#include <QResizeEvent>
#include <QSizePolicy>
#include <QStyleOptionTabBarBase>
#include <QTabBar>

#include <algorithm>
#include <cmath>

#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit {

// ============================================================================
// AdaptiveTabStrip::TabButton  (mirrors Python _CloseButtonSlot)
// ============================================================================

AdaptiveTabStrip::TabButton::TabButton(Button* button, int verticalOffset,
                                       QWidget* parent)
    : QWidget(parent), button_(button) {
  int offset = std::abs(verticalOffset);
  setFixedSize(button->width(), button->height() + offset * 2);
  button->setParent(this);
  button->move(0, std::max(0, offset * 2));
}

// ============================================================================
// AdaptiveTabStrip::AdaptiveTabBar  (mirrors Python _AdaptiveTabBar)
// ============================================================================

class AdaptiveTabStrip::AdaptiveTabBar final : public QTabBar {
 public:
  static constexpr double kRadius = 8.0;
  static constexpr int kMinWidth = 10;
  static constexpr double kWidthScale = 1.15;
  static constexpr int kSidePadding = 12;
  static constexpr int kHorizontalInset = 2;
  static constexpr int kTextSafety = 6;
  static constexpr int kCloseGap = 2;
  static constexpr int kCloseRightMargin = 2;
  static constexpr int kTextFade = 26;
  static constexpr double kSelectedShadowOffset = 0.5;
  static constexpr int kSelectedShadowSpread = 1;

  explicit AdaptiveTabBar(int closeButtonWidth, QWidget* parent)
      : QTabBar(parent), closeButtonWidth_(closeButtonWidth) {
    setAttribute(Qt::WA_StyledBackground, true);
    setAttribute(Qt::WA_OpaquePaintEvent, true);
    setMouseTracking(true);
    setDocumentMode(true);
    setDrawBase(false);
    setMovable(false);
    setExpanding(false);
    setUsesScrollButtons(true);
    setElideMode(Qt::ElideRight);
    setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Fixed);
  }

  void setVisualTabHeight(int height) {
    visualTabHeight_ = std::max(1, height);
    updateGeometry();
    update();
  }

  // --- QTabBar overrides ---

  QSize tabSizeHint(int index) const override {
    QSize size = QTabBar::tabSizeHint(index);
    int width = standardTabWidth(index) + closeButtonWidth_ + kCloseGap;
    return QSize(std::max(kMinWidth, width),
                 std::max(size.height(), visualTabHeight_));
  }

  int standardTabWidth(int index) const {
    int textWidth =
        QFontMetrics(font()).horizontalAdvance(tabText(index));
    int natural = textWidth + kSidePadding * 2 + kHorizontalInset + kTextSafety;
    return std::max(kMinWidth, static_cast<int>(std::round(natural * kWidthScale)));
  }

  int fullTabsWidth() const {
    int total = 0;
    for (int i = 0; i < count(); ++i) {
      total += standardTabWidth(i) + closeButtonWidth_ + kCloseGap;
    }
    return total;
  }

 protected:
  void paintEvent(QPaintEvent* event) override {
    positionTabButtons();
    auto pal = palette();
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing, true);
    painter.setClipRect(event->rect());
    painter.fillRect(rect(), QColor(pal.strip));

    // Draw non-selected tabs first
    for (int i = 0; i < count(); ++i) {
      if (i != currentIndex()) {
        paintVisibleTab(painter, i, event->rect(), pal);
      }
    }
    // Draw selected tab on top
    if (currentIndex() >= 0) {
      paintVisibleTab(painter, currentIndex(), event->rect(), pal);
    }
  }

  void mouseMoveEvent(QMouseEvent* event) override {
    int hover = tabAt(event->pos());
    if (hover != hoverIndex_) {
      hoverIndex_ = hover;
      update();
    }
    QTabBar::mouseMoveEvent(event);
  }

  void leaveEvent(QEvent* event) override {
    if (hoverIndex_ != -1) {
      hoverIndex_ = -1;
      update();
    }
    QTabBar::leaveEvent(event);
  }

  void resizeEvent(QResizeEvent* event) override {
    QTabBar::resizeEvent(event);
    positionTabButtons();
  }

  void tabLayoutChange() override {
    QTabBar::tabLayoutChange();
    positionTabButtons();
  }

 private:
  friend class AdaptiveTabStrip;

  struct TabPalette {
    QColor strip;
    QColor background;
    QColor border;
    QColor hover;
    QColor text;
  };

  TabPalette palette() const {
    auto c = [](const QString& token, const QString& fallback) -> QColor {
      auto value = Theme::tryGetColor(token);
      return value.has_value() && value->isValid() ? value.value()
                                                    : QColor(fallback);
    };
    return TabPalette{
        .strip = c(QStringLiteral("button.toggle.background.normal"),
                   QStringLiteral("#f0f0f0")),
        .background = c(QStringLiteral("Window"), QStringLiteral("#ffffff")),
        .border = c(QStringLiteral("separator.color"),
                    QStringLiteral("#e5e5e5")),
        .hover = c(QStringLiteral("button.toggle.background.hover"),
                   QStringLiteral("#e6e6e6")),
        .text = c(QStringLiteral("WindowText"), QStringLiteral("#1f1f1f")),
    };
  }

  void positionTabButtons() {
    for (int i = 0; i < count(); ++i) {
      QWidget* slot = tabButton(i, QTabBar::RightSide);
      if (slot == nullptr || !slot->isVisible()) {
        continue;
      }
      QRect tabRect = paintedTabRect(this->tabRect(i));
      int x = tabRect.right() - slot->width() - kCloseRightMargin + 1;
      int y = tabRect.center().y() - slot->height() / 2;
      slot->move(x, y);
    }
  }

  QRect paintedTabRect(const QRect& rect) const {
    int h = std::min(rect.height(), visualTabHeight_);
    int top = rect.top() + std::max(0, (rect.height() - h) / 2);
    return QRect(rect.left() + 1, top, std::max(0, rect.width() - 2), h);
  }

  void paintVisibleTab(QPainter& painter, int index, const QRect& exposedRect,
                       const TabPalette& pal) {
    QRect r = tabRect(index);
    if (r.isValid() && r.intersects(exposedRect)) {
      paintTab(painter, index, r, pal);
    }
  }

  void paintTab(QPainter& painter, int index, const QRect& rect,
                const TabPalette& pal) {
    bool selected = (index == currentIndex());
    bool hovered = !selected && (index == hoverIndex_);
    QRect tabRect = paintedTabRect(rect);

    if (selected) {
      paintSelectedShadow(painter, tabRect);
      paintSelectedBackground(painter, tabRect, pal);
    } else if (hovered) {
      painter.setPen(Qt::NoPen);
      painter.setBrush(QColor(pal.hover));
      painter.drawRoundedRect(tabRect, kRadius, kRadius);
    }

    int textRight = tabRect.right() - kSidePadding;
    QWidget* closeSlot = tabButton(index, QTabBar::RightSide);
    bool hasClose = (closeSlot != nullptr && closeSlot->isVisible());
    if (hasClose) {
      textRight = std::min(textRight, closeSlot->geometry().left() - kCloseGap);
    }
    QRect textRect(tabRect.left() + kSidePadding, tabRect.top(),
                   std::max(0, textRight - tabRect.left() - kSidePadding + 1),
                   tabRect.height());
    if (textRect.width() <= 0) {
      return;
    }

    QFontMetrics metrics(font());
    QString rawText = tabText(index);
    bool needsFade =
        hasClose && metrics.horizontalAdvance(rawText) > textRect.width();
    QString displayText =
        needsFade ? rawText
                  : metrics.elidedText(rawText, Qt::ElideRight,
                                        textRect.width());

    painter.setPen(QColor(pal.text));
    painter.save();
    painter.setClipRect(textRect);
    painter.drawText(textRect, Qt::AlignVCenter | Qt::AlignLeft, displayText);
    painter.restore();

    if (needsFade) {
      QLinearGradient fade(textRect.right() - kTextFade, 0,
                           textRect.right() + 1, 0);
      fade.setColorAt(0.0, QColor(0, 0, 0, 0));
      fade.setColorAt(1.0, QColor(pal.background));
      painter.fillRect(QRect(textRect.right() - kTextFade, tabRect.top(),
                              kTextFade + 1, tabRect.height()),
                       fade);
    }
  }

  void paintSelectedBackground(QPainter& painter, const QRect& rect,
                                const TabPalette& pal) {
    painter.setPen(Qt::NoPen);
    painter.setBrush(QColor(pal.background));
    painter.drawRoundedRect(rect, kRadius, kRadius);
    painter.setPen(QPen(QColor(pal.border), 1));
    painter.setBrush(Qt::NoBrush);
    painter.drawRoundedRect(rect, kRadius, kRadius);
  }

  void paintSelectedShadow(QPainter& painter, const QRect& rect) {
    if (rect.width() <= 0 || rect.height() <= 0) {
      return;
    }
    painter.save();
    painter.setClipRect(QRectF(rect.left() - 1, rect.bottom() - 1,
                                rect.width() + 2,
                                kSelectedShadowOffset + kSelectedShadowSpread + 3));
    painter.setPen(Qt::NoPen);

    QRectF softRect =
        QRectF(rect).adjusted(0, kSelectedShadowOffset, 0,
                               kSelectedShadowOffset + kSelectedShadowSpread);
    painter.setBrush(QColor(0, 0, 0, 55));
    painter.drawRoundedRect(softRect, kRadius, kRadius);

    QRectF coreRect =
        QRectF(rect).adjusted(1, kSelectedShadowOffset - 1, -1,
                               kSelectedShadowOffset);
    painter.setBrush(QColor(0, 0, 0, 125));
    painter.drawRoundedRect(coreRect, kRadius - 1, kRadius - 1);
    painter.restore();
  }

  int closeButtonWidth_ = 28;
  int visualTabHeight_ = 36;
  int hoverIndex_ = -1;
};

// ============================================================================
// AdaptiveTabStrip
// ============================================================================

AdaptiveTabStrip::AdaptiveTabStrip(const Config& config, QWidget* parent)
    : QWidget(parent),
      closePolicy_(config.closePolicy),
      singleTabClosable_(config.singleTabClosable),
      closeIcon_(config.closeIcon),
      closeButtonSize_(config.closeButtonSize),
      closeIconSize_(config.closeIconSize),
      closeButtonVerticalOffset_(config.closeButtonVerticalOffset) {
  tabBar_ = new AdaptiveTabBar(closeButtonSize_, this);

  Button::Config btnCfg;
  btnCfg.icon = config.addIcon;
  btnCfg.menu = config.addButtonMenu;
  addButton_ = new Button(btnCfg, this);

  int plusHeight = std::max(
      {addButton_->sizeHint().height(), addButton_->minimumHeight(),
       addButton_->height()});
  tabBar_->setVisualTabHeight(plusHeight);
  tabBar_->setMinimumHeight(
      plusHeight +
      static_cast<int>(
          std::ceil(AdaptiveTabBar::kSelectedShadowOffset +
                    AdaptiveTabBar::kSelectedShadowSpread)));

  layout_ = new QHBoxLayout(this);
  layout_->setContentsMargins(config.marginLeft, config.marginTop,
                               config.marginRight, config.marginBottom);
  layout_->setSpacing(config.spacing);
  layout_->addWidget(tabBar_);
  layout_->addWidget(addButton_, 0, Qt::AlignBottom);
  layout_->addStretch(1);

  connect(tabBar_, &QTabBar::currentChanged, this,
          &AdaptiveTabStrip::onCurrentChanged);
  connect(addButton_, &QAbstractButton::clicked, this,
          &AdaptiveTabStrip::addRequested);
}

AdaptiveTabStrip::~AdaptiveTabStrip() = default;

void AdaptiveTabStrip::onCurrentChanged(int index) {
  refreshCloseButtons();
  emit currentChanged(index);
}

void AdaptiveTabStrip::resizeEvent(QResizeEvent* event) {
  QWidget::resizeEvent(event);
  refreshCloseButtons();
}

void AdaptiveTabStrip::refreshCloseButtons() {
  if (updatingCloseButtons_) {
    return;
  }
  updatingCloseButtons_ = true;
  int cnt = count();
  bool showAll = shouldShowAllCloseButtons();
  for (int i = 0; i < cnt; ++i) {
    QWidget* existing =
        tabBar_->tabButton(i, QTabBar::RightSide);
    bool shouldShow = shouldShowCloseButton(i, cnt, showAll);
    if (shouldShow && existing == nullptr) {
      tabBar_->setTabButton(i, QTabBar::RightSide, createCloseSlot());
    } else if (!shouldShow && existing != nullptr) {
      tabBar_->setTabButton(i, QTabBar::RightSide, nullptr);
    }
  }
  updatingCloseButtons_ = false;
}

bool AdaptiveTabStrip::shouldShowAllCloseButtons() const {
  if (closePolicy_ == CloseButtonPolicy::All) {
    return true;
  }
  if (closePolicy_ == CloseButtonPolicy::CurrentOnly) {
    return false;
  }
  // AllWhenFitElseCurrent
  auto margins = layout_->contentsMargins();
  int available = contentsRect().width() - margins.left() - margins.right() -
                  std::max(addButton_->width(),
                           addButton_->sizeHint().width()) -
                  layout_->spacing();
  return tabBar_->fullTabsWidth() <= available;
}

bool AdaptiveTabStrip::shouldShowCloseButton(int index, int count,
                                              bool showAll) const {
  if (count <= 0 || (count == 1 && !singleTabClosable_)) {
    return false;
  }
  return showAll || index == currentIndex();
}

QWidget* AdaptiveTabStrip::createCloseSlot() {
  Button::Config btnCfg;
  btnCfg.icon = closeIcon_;
  btnCfg.size = QSize(closeButtonSize_, closeButtonSize_);
  btnCfg.iconSize = closeIconSize_;
  btnCfg.variant = Button::Variant::Ghost;
  btnCfg.cornerRadius = 5;

  auto* button = new Button(btnCfg);
  button->setFocusPolicy(Qt::NoFocus);

  auto* slot =
      new TabButton(button, closeButtonVerticalOffset_, tabBar_);
  connect(button, &QAbstractButton::clicked, this,
          [this, slot]() { emitCloseForSlot(slot); });
  return slot;
}

void AdaptiveTabStrip::emitCloseForSlot(QWidget* slot) {
  for (int i = 0; i < count(); ++i) {
    if (tabBar_->tabButton(i, QTabBar::RightSide) == slot) {
      emit tabCloseRequested(i);
      return;
    }
  }
}

// --- QTabBar-like compatibility API ---

int AdaptiveTabStrip::addTab(const QString& text) {
  int index = tabBar_->addTab(text);
  refreshCloseButtons();
  return index;
}

void AdaptiveTabStrip::removeTab(int index) {
  tabBar_->removeTab(index);
  refreshCloseButtons();
}

int AdaptiveTabStrip::count() const { return tabBar_->count(); }

int AdaptiveTabStrip::currentIndex() const {
  return tabBar_->currentIndex();
}

void AdaptiveTabStrip::setCurrentIndex(int index) {
  tabBar_->setCurrentIndex(index);
}

void AdaptiveTabStrip::setTabData(int index, const QVariant& data) {
  tabBar_->setTabData(index, data);
}

QVariant AdaptiveTabStrip::tabData(int index) const {
  return tabBar_->tabData(index);
}

void AdaptiveTabStrip::setTabToolTip(int index, const QString& text) {
  tabBar_->setTabToolTip(index, text);
}

QWidget* AdaptiveTabStrip::tabButton(int index,
                                      QTabBar::ButtonPosition position) const {
  return tabBar_->tabButton(index, position);
}

QRect AdaptiveTabStrip::tabRect(int index) const {
  return tabBar_->tabRect(index);
}

}  // namespace sli::toolkit