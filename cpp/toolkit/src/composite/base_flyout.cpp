#include "sli/toolkit/composite/base_flyout.h"

#include <cmath>
#include <optional>

#include <QButtonGroup>
#include <QGuiApplication>
#include <QHBoxLayout>
#include <QKeyEvent>
#include <QPainter>
#include <QPen>
#include <QPropertyAnimation>
#include <QScreen>
#include <QStyle>
#include <QVariant>
#include <QVBoxLayout>

#include "sli/toolkit/atomic/radio_button.h"
#include "sli/toolkit/atomic/text_labels.h"
#include "sli/toolkit/composite/color_swatch.h"
#include "sli/toolkit/helpers/hover_coordinator.h"
#include "sli/toolkit/helpers/shadow_painter.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit {

// ─── singleton state ──────────────────────────────────────────────────────────

QPointer<BaseFlyout> BaseFlyout::activeFlyout_;

// ─── constructor / destructor ─────────────────────────────────────────────────

BaseFlyout::BaseFlyout(QWidget* parent) : QWidget(parent) {
  Q_ASSERT_X(parent != nullptr, "BaseFlyout",
             "BaseFlyout requires an in-window parent widget");

  setWindowFlags(Qt::Widget);
  setAttribute(Qt::WA_TranslucentBackground);

  // attach_in_window_widget: walk up to window and use it as overlay.
  // In the C++ port there is no external overlay-layer manager; we simply
  // parent to the top-level window (mirrors attach_in_window_widget behavior
  // when no overlay resolver is registered).
  overlayLayer_ = nullptr;  // no resolved overlay layer in C++ port
  // Re-parent to the window so the widget can float above siblings.
  if (QWidget* win = parent->window()) {
    setParent(win);
  }

  // create_shadow_surface:
  //   outer_margins = (SHADOW_RADIUS, SHADOW_RADIUS, SHADOW_RADIUS, SHADOW_RADIUS)
  //   container objectName = "FlyoutContainer", WA_StyledBackground = true
  //   content_layout margins = (4, 4, 4, 4), spacing = 4
  mainLayout_ = new QVBoxLayout(this);
  mainLayout_->setContentsMargins(SHADOW_RADIUS, SHADOW_RADIUS,
                                   SHADOW_RADIUS, SHADOW_RADIUS);

  container_ = new QWidget(this);
  container_->setObjectName(QStringLiteral("FlyoutContainer"));
  container_->setAttribute(Qt::WA_StyledBackground, true);
  mainLayout_->addWidget(container_);

  contentLayout_ = new QVBoxLayout(container_);
  contentLayout_->setContentsMargins(4, 4, 4, 4);
  contentLayout_->setSpacing(4);

  // theme_manager.theme_changed.connect(_apply_base_style)
  Theme::onThemeChanged(this, [this]() { applyBaseStyle(); });
  applyBaseStyle();

  // flyout_manager.register_flyout(self)
  registerWithManager();
  connect(this, &QObject::destroyed, this, [this]() {
    unregisterFromManager();
  });

  setFocusPolicy(Qt::StrongFocus);
}

BaseFlyout::~BaseFlyout() {
  unregisterFromManager();
}

// ─── FlyoutManager singleton (inlined) ───────────────────────────────────────

void BaseFlyout::registerWithManager() {
  // no-op: activeFlyout_ state is managed by requestShow/requestHide
}

void BaseFlyout::unregisterFromManager() {
  if (activeFlyout_ == this) {
    activeFlyout_.clear();
  }
}

void BaseFlyout::requestShow() {
  // Hide any other active flyout (mirrors FlyoutManager.request_show).
  if (activeFlyout_ != nullptr && activeFlyout_ != this) {
    activeFlyout_->hide();
  }
  activeFlyout_ = this;
}

void BaseFlyout::requestHide() {
  if (activeFlyout_ == this) {
    activeFlyout_.clear();
  }
}

// ─── _apply_base_style ────────────────────────────────────────────────────────

void BaseFlyout::applyBaseStyle() {
  container_->style()->unpolish(container_);
  container_->style()->polish(container_);
  container_->update();
}

// ─── builder helpers ──────────────────────────────────────────────────────────

void BaseFlyout::addWidget(QWidget* widget) {
  contentLayout_->addWidget(widget);
}

// add_section: Label(text, pixel_size=12, bold=True, color_token="dialog.text")
Label* BaseFlyout::addSection(const QString& text, int /*pixelSize*/) {
  // Python: pixel_size=12 default, bold=True. C++ Label uses string variant names.
  // "group-title" = 13px + bold, matches Python intent.
  auto* label = new Label(text, QStringLiteral("group-title"), container_);
  contentLayout_->addWidget(label);
  return label;
}

// add_row: host QWidget, QHBoxLayout, margins=(0,0,0,0), spacing=8,
//          label left, optional stretch, widget right.
Label* BaseFlyout::addRow(const QString& labelText, QWidget* widget,
                          int /*labelPixelSize*/,
                          bool stretchBeforeWidget) {
  auto* host = new QWidget(container_);
  auto* row = new QHBoxLayout(host);
  row->setContentsMargins(0, 0, 0, 0);
  row->setSpacing(8);

  auto* label = new Label(labelText, QStringLiteral("caption"), host);
  row->addWidget(label);
  if (stretchBeforeWidget) {
    row->addStretch();
  }
  widget->setParent(host);
  row->addWidget(widget);

  contentLayout_->addWidget(host);
  return label;
}

// add_radio_row: label (pixel_size=11), host+HBox (margins=0, spacing=8),
//               QButtonGroup, RadioButtons, trailing stretch.
// Mirrors Python: default=None → first checked; default=value → match by value.
Label* BaseFlyout::addRadioRow(const QString& labelText,
                                const QList<QPair<QString, QVariant>>& options,
                                QButtonGroup* group,
                                const QVariant& defaultValue) {
  auto* label = new Label(labelText, QStringLiteral("caption"), container_);
  contentLayout_->addWidget(label);

  auto* host = new QWidget(container_);
  auto* row = new QHBoxLayout(host);
  row->setContentsMargins(0, 0, 0, 0);
  row->setSpacing(8);

  for (int i = 0; i < options.size(); ++i) {
    const auto& [text, value] = options[i];
    auto* rb = new RadioButton(text, host);
    // default is None → i==0 checked; otherwise match by value.
    if ((!defaultValue.isValid() && i == 0) || value == defaultValue) {
      rb->setChecked(true);
    }
    group->addButton(rb);
    row->addWidget(rb);
  }
  row->addStretch();
  contentLayout_->addWidget(host);
  return label;
}

// make_color_swatch: ColorSwatch(color=color, size=size, alpha=alpha, parent=self)
ColorSwatch* BaseFlyout::makeColorSwatch(const QColor& color, int size,
                                          bool alpha) {
  return new ColorSwatch(color, size, alpha, this);
}

// ─── _ensure_overlay_parent ───────────────────────────────────────────────────

void BaseFlyout::ensureOverlayParent(QWidget* anchor) {
  if (anchor == nullptr) {
    return;
  }
  // In C++ port: if we are not yet parented to the anchor's window, re-parent.
  QWidget* win = anchor->window();
  if (win != nullptr && parentWidget() != win) {
    const bool wasVisible = isVisible();
    setParent(win);
    if (wasVisible) {
      QWidget::show();
      raise();
    }
  }
}

// ─── paintEvent ───────────────────────────────────────────────────────────────

void BaseFlyout::paintEvent(QPaintEvent*) {
  QPainter painter(this);
  // paint_shadowed_surface: setRenderHint(Antialiasing) + drawRoundedShadow
  painter.setRenderHint(QPainter::Antialiasing);
  const QRect containerRect = container_->geometry();
  drawRoundedShadow(painter, QRectF(containerRect), SHADOW_RADIUS,
                    CONTENT_RADIUS);

  // Fill container rect with flyout.background, stroke with flyout.border.
  const QColor bg = Theme::getColor(QStringLiteral("flyout.background"));
  const QColor border = Theme::getColor(QStringLiteral("flyout.border"));
  painter.setBrush(QBrush(bg));
  painter.setPen(QPen(border, 1));
  painter.drawRoundedRect(containerRect, CONTENT_RADIUS, CONTENT_RADIUS);
  painter.end();
}

// ─── static geometry helpers ─────────────────────────────────────────────────

// _parse_point: "bottom-left" → (fx, fy) fractions
std::pair<double, double> BaseFlyout::parsePoint(const QString& spec) {
  // _H_AXIS = {left:0.0, center:0.5, right:1.0}
  // _V_AXIS = {top:0.0, center:0.5, bottom:1.0}
  auto hAxis = [](const QString& s) -> std::optional<double> {
    if (s == QLatin1String("left"))   return 0.0;
    if (s == QLatin1String("center")) return 0.5;
    if (s == QLatin1String("right"))  return 1.0;
    return std::nullopt;
  };
  auto vAxis = [](const QString& s) -> std::optional<double> {
    if (s == QLatin1String("top"))    return 0.0;
    if (s == QLatin1String("center")) return 0.5;
    if (s == QLatin1String("bottom")) return 1.0;
    return std::nullopt;
  };

  // parts = spec.split("-") if "-" in spec else [spec, "center"]
  QStringList parts =
      spec.contains(QLatin1Char('-')) ? spec.split(QLatin1Char('-'))
                                      : QStringList{spec, QStringLiteral("center")};
  // (parts + ["center"])[:2]
  while (parts.size() < 2) {
    parts << QStringLiteral("center");
  }
  QString v = parts[0];
  QString h = parts[1];

  // if v in _H_AXIS and h in _V_AXIS: v, h = h, v
  if (hAxis(v).has_value() && vAxis(h).has_value()) {
    std::swap(v, h);
  }

  const double fx = hAxis(h).value_or(0.5);
  const double fy = vAxis(v).value_or(0.5);
  return {fx, fy};
}

// _point_in_rect
QPoint BaseFlyout::pointInRect(const QRect& rect, const QString& spec) {
  const auto [fx, fy] = parsePoint(spec);
  return QPoint(
      static_cast<int>(std::round(rect.left() + fx * rect.width())),
      static_cast<int>(std::round(rect.top() + fy * rect.height())));
}

// ─── surface_anchor_rect (inlined from in_window_surface.py) ─────────────────

QRect BaseFlyout::surfaceAnchorRect(QWidget* anchor) const {
  // No external overlay_layer in C++ port → fall back to parent-relative coords.
  QWidget* parent = parentWidget();
  if (parent != nullptr && !isWindow()) {
    return QRect(anchor->mapTo(parent, QPoint(0, 0)), anchor->size());
  }
  return QRect(anchor->mapToGlobal(QPoint(0, 0)), anchor->size());
}

// surface_available_rect (margin=0)
QRect BaseFlyout::surfaceAvailableRect(QWidget* anchor, int margin) const {
  QWidget* parent = parentWidget();
  QRect available;
  if (parent != nullptr && !isWindow()) {
    available = parent->rect();
  } else {
    QScreen* screen = nullptr;
    if (anchor != nullptr) {
      screen = anchor->screen();
    }
    if (screen == nullptr) {
      screen = QGuiApplication::primaryScreen();
    }
    available = screen != nullptr ? screen->availableGeometry()
                                   : QRect(0, 0, 1, 1);
  }
  if (margin != 0) {
    return available.adjusted(margin, margin, -margin, -margin);
  }
  return available;
}

// clamp_surface_rect
QRect BaseFlyout::clampSurfaceRect(const QRect& rect, const QRect& available) {
  QRect result = rect;
  if (result.right() > available.right()) {
    result.moveRight(available.right());
  }
  if (result.left() < available.left()) {
    result.moveLeft(available.left());
  }
  if (result.bottom() > available.bottom()) {
    result.moveBottom(available.bottom());
  }
  if (result.top() < available.top()) {
    result.moveTop(available.top());
  }
  return result;
}

// place_surface_rect (inlined from in_window_surface.py, position string branch)
QRect BaseFlyout::placeSurfaceRect(QWidget* anchor, const QSize& size,
                                    const QString& position, int offset,
                                    int margin) const {
  const QRect anchorRect = surfaceAnchorRect(anchor);
  const QRect available = surfaceAvailableRect(anchor, margin);

  const int cx = anchorRect.x() + (anchorRect.width() - size.width()) / 2;
  const int cy = anchorRect.y() + (anchorRect.height() - size.height()) / 2;
  const int w = size.width();
  const int h = size.height();

  QRect target;
  if (position == QLatin1String("top")) {
    target = QRect(cx, anchorRect.top() - h - offset, w, h);
    const QRect fallback = QRect(cx, anchorRect.bottom() + offset, w, h);
    if (target.top() < available.top() && fallback.bottom() <= available.bottom()) {
      target = fallback;
    }
  } else if (position == QLatin1String("left")) {
    target = QRect(anchorRect.left() - w - offset, cy, w, h);
    const QRect fallback = QRect(anchorRect.right() + offset, cy, w, h);
    if (target.left() < available.left() && fallback.right() <= available.right()) {
      target = fallback;
    }
  } else if (position == QLatin1String("right")) {
    target = QRect(anchorRect.right() + offset, cy, w, h);
    const QRect fallback = QRect(anchorRect.left() - w - offset, cy, w, h);
    if (target.right() > available.right() && fallback.left() >= available.left()) {
      target = fallback;
    }
  } else if (position == QLatin1String("top-left")) {
    target = QRect(anchorRect.left() - w - offset,
                   anchorRect.top() - h - offset, w, h);
    if (target.left() < available.left()) {
      target.moveLeft(anchorRect.right() + offset);
    }
    if (target.top() < available.top()) {
      target.moveTop(anchorRect.bottom() + offset);
    }
  } else if (position == QLatin1String("top-right")) {
    target = QRect(anchorRect.right() + offset,
                   anchorRect.top() - h - offset, w, h);
    if (target.right() > available.right()) {
      target.moveRight(anchorRect.left() - offset);
    }
    if (target.top() < available.top()) {
      target.moveTop(anchorRect.bottom() + offset);
    }
  } else if (position == QLatin1String("bottom-left")) {
    target = QRect(anchorRect.left() - w - offset,
                   anchorRect.bottom() + offset, w, h);
    if (target.left() < available.left()) {
      target.moveLeft(anchorRect.right() + offset);
    }
    if (target.bottom() > available.bottom()) {
      target.moveBottom(anchorRect.top() - offset);
    }
  } else if (position == QLatin1String("bottom-right")) {
    target = QRect(anchorRect.right() + offset,
                   anchorRect.bottom() + offset, w, h);
    if (target.right() > available.right()) {
      target.moveRight(anchorRect.left() - offset);
    }
    if (target.bottom() > available.bottom()) {
      target.moveBottom(anchorRect.top() - offset);
    }
  } else {
    // "bottom" (default)
    target = QRect(cx, anchorRect.bottom() + offset, w, h);
    const QRect fallback = QRect(cx, anchorRect.top() - h - offset, w, h);
    if (target.bottom() > available.bottom() && fallback.top() >= available.top()) {
      target = fallback;
    }
  }
  return clampSurfaceRect(target, available);
}

// ─── _overlay_rect_relative_to_anchor ────────────────────────────────────────

QRect BaseFlyout::overlayRectRelativeToAnchor(QWidget* anchor,
                                               const QSize& size,
                                               const QString& position,
                                               int offset) const {
  // In C++ port there is no overlay_layer object with
  // place_rect_relative_to_anchor method, so always delegate to
  // placeSurfaceRect (mirrors the else branch in Python).
  return placeSurfaceRect(anchor, size, position, offset, 0);
}

// ─── showAligned ─────────────────────────────────────────────────────────────

void BaseFlyout::showAligned(QWidget* anchorWidget,
                              const QString& anchorPoint,
                              const QString& flyoutPoint,
                              const QString& position,
                              int offset,
                              const QString& animation,
                              int animationDurationMs,
                              int animationDistance,
                              QEasingCurve::Type easing) {
  anchorWidget_ = anchorWidget;
  ensureOverlayParent(anchorWidget);

  requestShow();

  // Invalidate / activate container layout before measuring.
  if (container_->layout() != nullptr) {
    container_->layout()->invalidate();
    container_->layout()->activate();
    container_->updateGeometry();
  }
  adjustSize();
  const QSize flyoutSize = size();

  const QRect anchorRect = surfaceAnchorRect(anchorWidget);

  QRect finalRect;
  QPoint flyoutCenter;

  if (!position.isEmpty()) {
    // Legacy position= compat path: _overlay_rect_relative_to_anchor
    finalRect = overlayRectRelativeToAnchor(
        anchorWidget, flyoutSize, position, offset - SHADOW_RADIUS);
    flyoutCenter = finalRect.center();
  } else {
    // anchor_point / flyout_point path
    const QPoint anchorPt = pointInRect(anchorRect, anchorPoint);
    const QPoint flyoutPtLocal =
        pointInRect(QRect(QPoint(0, 0), flyoutSize), flyoutPoint);

    QPoint topLeft(anchorPt.x() - flyoutPtLocal.x(),
                   anchorPt.y() - flyoutPtLocal.y());

    flyoutCenter = QPoint(topLeft.x() + flyoutSize.width() / 2,
                          topLeft.y() + flyoutSize.height() / 2);

    const int dirX = flyoutCenter.x() - anchorRect.center().x();
    const int dirY = flyoutCenter.y() - anchorRect.center().y();
    const double length = std::hypot(static_cast<double>(dirX),
                                     static_cast<double>(dirY));
    const int push = offset - SHADOW_RADIUS;
    if (length > 0.0 && push != 0) {
      const double ux = dirX / length;
      const double uy = dirY / length;
      topLeft = QPoint(topLeft.x() + static_cast<int>(std::round(push * ux)),
                       topLeft.y() + static_cast<int>(std::round(push * uy)));
    }
    finalRect = clampSurfaceRect(QRect(topLeft, flyoutSize),
                                  surfaceAvailableRect(anchorWidget, 0));
    flyoutCenter = finalRect.center();
  }

  // Compute direction unit vector for animation.
  const int dirX2 = flyoutCenter.x() - anchorRect.center().x();
  const int dirY2 = flyoutCenter.y() - anchorRect.center().y();
  const double length2 = std::hypot(static_cast<double>(dirX2),
                                     static_cast<double>(dirY2));
  double ux = 0.0;
  double uy = 0.0;
  if (length2 > 0.0) {
    ux = dirX2 / length2;
    uy = dirY2 / length2;
  }

  const QString mode = animation.isEmpty() ? QStringLiteral("none") : animation;

  if (mode == QLatin1String("none")) {
    setGeometry(finalRect);
    QWidget::show();
    raise();
    return;
  }

  // animation == "slide"
  // default duration = get_flyout_timings().flyout_animation_duration_ms = 160
  const int duration = (animationDurationMs >= 0) ? animationDurationMs : 160;

  if (showAnimation_ != nullptr) {
    showAnimation_->stop();
    showAnimation_->deleteLater();
    showAnimation_ = nullptr;
  }

  // Slide starts toward the anchor (opposite of push direction).
  const double slideDx = (length2 > 0.0) ? -ux * animationDistance : 0.0;
  const double slideDy = (length2 > 0.0) ? -uy * animationDistance : 0.0;
  const QPoint startPos(finalRect.x() + static_cast<int>(std::round(slideDx)),
                        finalRect.y() + static_cast<int>(std::round(slideDy)));

  setGeometry(QRect(startPos, finalRect.size()));
  // Block mouse events during animation to prevent accidental hover highlights.
  setAttribute(Qt::WA_TransparentForMouseEvents, true);
  QWidget::show();
  raise();

  auto* anim = new QPropertyAnimation(this, QByteArrayLiteral("pos"), this);
  anim->setDuration(duration);
  anim->setStartValue(startPos);
  anim->setEndValue(QPoint(finalRect.x(), finalRect.y()));
  anim->setEasingCurve(easing);
  connect(anim, &QPropertyAnimation::finished,
          this, &BaseFlyout::onShowAnimationFinished);
  showAnimation_ = anim;
  anim->start();
}

// ─── _on_show_animation_finished ─────────────────────────────────────────────

void BaseFlyout::onShowAnimationFinished() {
  if (showAnimation_ != nullptr) {
    showAnimation_->deleteLater();
    showAnimation_ = nullptr;
  }
  setAttribute(Qt::WA_TransparentForMouseEvents, false);
  // hover_coordinator().reconcile()
  hoverCoordinator().reconcile();
}

// ─── contains_global / anchor_contains_global ────────────────────────────────

bool BaseFlyout::containsGlobal(const QPoint& globalPos) const {
  if (!isVisible()) {
    return false;
  }
  // No overlay_layer in C++ port → direct rect check.
  return rect().contains(mapFromGlobal(globalPos));
}

bool BaseFlyout::anchorContainsGlobal(const QPoint& globalPos) const {
  if (anchorWidget_.isNull()) {
    return false;
  }
  const QPoint topLeft = anchorWidget_->mapToGlobal(QPoint(0, 0));
  return QRect(topLeft, anchorWidget_->size()).contains(globalPos);
}

QList<QWidget*> BaseFlyout::anchorWidgets() const {
  QList<QWidget*> result;
  if (!anchorWidget_.isNull()) {
    result << anchorWidget_.data();
  }
  return result;
}

// ─── hide / show ──────────────────────────────────────────────────────────────

void BaseFlyout::hide() {
  requestHide();
  QWidget::hide();

  // Restore focus to parent window.
  if (parent() != nullptr) {
    QWidget* win = static_cast<QObject*>(parent())->isWidgetType()
                       ? static_cast<QWidget*>(parent())->window()
                       : nullptr;
    if (win != nullptr) {
      win->activateWindow();
      win->setFocus();
    }
  }
}

void BaseFlyout::show() {
  requestShow();
  QWidget::show();
}

// ─── keyPressEvent ────────────────────────────────────────────────────────────

void BaseFlyout::keyPressEvent(QKeyEvent* event) {
  if (event->key() == Qt::Key_Escape) {
    hide();
    event->accept();
    return;
  }
  QWidget::keyPressEvent(event);
}

}  // namespace sli::toolkit
