#include "sli/toolkit/composite/unified_flyout/panel.h"

#include <QApplication>
#include <QCloseEvent>
#include <QGuiApplication>
#include <QHideEvent>
#include <QPainter>
#include <QResizeEvent>
#include <QScreen>
#include <QVBoxLayout>

#include "sli/toolkit/composite/unified_flyout/delegate.h"
#include "sli/toolkit/composite/unified_flyout/layout.h"
#include "sli/toolkit/composite/unified_flyout/overlay_list_view.h"
#include "sli/toolkit/composite/unified_flyout/style.h"
#include "sli/toolkit/theme.h"

using sli::toolkit::unified_flyout::kShadowRadius;

namespace sli::toolkit::unified_flyout {

Panel::Panel(QWidget* parent)
    : QWidget(parent, Qt::Popup | Qt::FramelessWindowHint) {
  setAttribute(Qt::WA_TranslucentBackground);
  setFocusPolicy(Qt::StrongFocus);

  // Container widget inside the shadow margin — mirrors Python's
  // container_widget with surfaceRole = "container".
  container_ = new QWidget(this);
  container_->setObjectName(QStringLiteral("FlyoutWidget"));
  container_->setAttribute(Qt::WA_StyledBackground, true);

  auto* layout = new QVBoxLayout(this);
  layout->setContentsMargins(kShadowRadius, kShadowRadius,
                             kShadowRadius, kShadowRadius);
  layout->addWidget(container_);

  auto* innerLayout = new QVBoxLayout(container_);
  innerLayout->setContentsMargins(style_.panelMargin, style_.panelMargin,
                                  style_.panelMargin, style_.panelMargin);

  model_ = new FlyoutListModel(this);
  delegate_ = new ItemDelegate(this);
  delegate_->setItemHeight(style_.itemHeight);
  view_ = new OverlayListView(this);
  view_->setModel(model_);
  view_->setItemDelegate(delegate_);
  innerLayout->addWidget(view_);

  // Rounded clip on the container — Python's _container_clip.
  clipEffect_ = std::make_unique<RoundedClipEffect>(style_.cornerRadius);
  container_->setGraphicsEffect(clipEffect_.get());

  connect(view_, &QListView::clicked, this, &Panel::onIndexClicked);
  connect(view_, &OverlayListView::escapePressed, this, [this]() {
    close();
  });

  // Python: `self.theme_manager.theme_changed.connect(self._apply_style)`
  sli::toolkit::Theme::onThemeChanged(this, [this] { applyStyle(); });
  applyStyle();
}

Panel::~Panel() = default;

void Panel::setMode(FlyoutMode mode) { mode_ = mode; }

void Panel::setStyle(const FlyoutStyle& style) {
  style_ = style;
  delegate_->setItemHeight(style.itemHeight);
  if (clipEffect_) {
    clipEffect_->setRadius(style.cornerRadius);
  }
}

void Panel::setItems(std::vector<FlyoutItem> items) {
  model_->setItems(std::move(items));
}

void Panel::setCurrentIndex(int index) { model_->setCurrentIndex(index); }

int Panel::currentIndex() const { return model_->currentIndex(); }

void Panel::showForAnchor(QWidget* anchor) {
  const QSize sz = sizeHint();
  resize(sz.expandedTo(QSize(180, 200)));
  QRect screenAvail;
  if (auto* screen = QGuiApplication::primaryScreen()) {
    screenAvail = screen->availableGeometry();
  }
  const auto placement = computePlacement(anchor, size(), screenAvail);
  move(placement.topLeft);
  applyContainerGeometry();
  show();
  view_->setFocus(Qt::OtherFocusReason);
}

// ---------------------------------------------------------------------------
// Style — mirrors Python _UnifiedFlyoutStyleMixin
// ---------------------------------------------------------------------------

void Panel::applyStyle() {
  // Python: paint the panel surface through QSS.
  // C++: we do it in paintEvent with theme tokens.
  const QColor bg = sli::toolkit::Theme::getColor(
      QStringLiteral("flyout.background"));
  const QColor border = sli::toolkit::Theme::getColor(
      QStringLiteral("flyout.border"));

  // Apply background/border to container via stylesheet (Python's approach).
  container_->setStyleSheet(
      QStringLiteral(
          "#FlyoutWidget {"
          "background-color: %1;"
          "border: 1px solid %2;"
          "border-radius: %3px;"
          "}")
          .arg(bg.name(QColor::HexArgb))
          .arg(border.name(QColor::HexArgb))
          .arg(style_.cornerRadius));

  view_->setStyleSheet(
      QStringLiteral("background-color: transparent; border: none;"));
}

void Panel::applyContainerGeometry() {
  // Python: inner_rect = self.rect().adjusted(SHADOW, SHADOW, -SHADOW, -SHADOW)
  const QRect innerRect = rect().adjusted(
      kShadowRadius, kShadowRadius, -kShadowRadius, -kShadowRadius);
  if (container_->geometry() != innerRect) {
    container_->setGeometry(innerRect);
  }
}

void Panel::drawShadow(QPainter* painter, const QRectF& rect, int steps) {
  drawRoundedShadow(painter, rect, steps, style_.cornerRadius);
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

void Panel::paintEvent(QPaintEvent*) {
  QPainter painter(this);
  painter.setRenderHint(QPainter::Antialiasing);
  painter.setPen(Qt::NoPen);

  // Draw shadow around the container — Python's `_draw_shadow`.
  drawShadow(&painter, QRectF(container_->geometry()), kShadowRadius);
}

void Panel::resizeEvent(QResizeEvent* event) {
  QWidget::resizeEvent(event);
  applyContainerGeometry();
}

void Panel::hideEvent(QHideEvent* event) {
  QWidget::hideEvent(event);
}

void Panel::closeEvent(QCloseEvent* event) {
  emit closed();
  QWidget::closeEvent(event);
}

void Panel::onIndexClicked(const QModelIndex& index) {
  if (index.isValid()) {
    emit itemActivated(index.row());
    close();
  }
}

}  // namespace sli::toolkit::unified_flyout