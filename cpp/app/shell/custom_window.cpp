#include "shell/custom_window.h"

#include "sli/toolkit/theme.h"

#include <QApplication>
#include <QEnterEvent>
#include <QEvent>
#include <QHBoxLayout>
#include <QKeySequence>
#include <QLabel>
#include <QMouseEvent>
#include <QPainter>
#include <QShortcut>
#include <QToolButton>
#include <QVariantAnimation>
#include <QVBoxLayout>
#include <QWidget>
#include <QWindow>

#include <cmath>
#include <functional>

namespace imgsli::app {
namespace {

class WindowControlButton final : public QToolButton {
 public:
  explicit WindowControlButton(const QString &glyph, const QColor &hoverColor,
                               QWidget *parent)
      : QToolButton(parent), hoverColor_(hoverColor), animation_(this) {
    setText(glyph);
    setFixedSize(46, 32);
    setCursor(Qt::PointingHandCursor);
    setFocusPolicy(Qt::NoFocus);
    const QColor glyphColor = sli::toolkit::Theme::palette().windowText;
    setStyleSheet(QStringLiteral(
                      "QToolButton { background: transparent; color: %1; "
                      "border: 0; }")
                      .arg(glyphColor.name()));
    setProperty("hoverRippleEnabled", true);

    animation_.setDuration(140);
    animation_.setEasingCurve(QEasingCurve::OutCubic);
    connect(&animation_, &QVariantAnimation::valueChanged, this,
            [this](const QVariant &value) {
              rippleProgress_ = value.toReal();
              update();
            });
  }

 protected:
  void enterEvent(QEnterEvent *event) override {
    rippleOrigin_ = event->position();
    animateTo(1.0);
    QToolButton::enterEvent(event);
  }

  void leaveEvent(QEvent *event) override {
    animateTo(0.0);
    QToolButton::leaveEvent(event);
  }

  void mouseMoveEvent(QMouseEvent *event) override {
    rippleOrigin_ = event->position();
    QToolButton::mouseMoveEvent(event);
  }

  void paintEvent(QPaintEvent *event) override {
    if (rippleProgress_ > 0.0) {
      QPainter painter(this);
      painter.setRenderHint(QPainter::Antialiasing);
      painter.setClipRect(rect());
      QColor color = hoverColor_;
      color.setAlphaF(color.alphaF() * rippleProgress_);
      painter.setBrush(color);
      painter.setPen(Qt::NoPen);
      const qreal radius =
          std::hypot(static_cast<qreal>(width()), static_cast<qreal>(height())) *
          rippleProgress_;
      painter.drawEllipse(rippleOrigin_, radius, radius);
    }
    QToolButton::paintEvent(event);
  }

 private:
  void animateTo(qreal target) {
    animation_.stop();
    animation_.setStartValue(rippleProgress_);
    animation_.setEndValue(target);
    animation_.start();
  }

  QColor hoverColor_;
  QPointF rippleOrigin_;
  QVariantAnimation animation_;
  qreal rippleProgress_ = 0.0;
};

// Internal title bar widget. Owns the drag region for the system move
// and the three window control buttons.
class TitleBar final : public QWidget {
 public:
  explicit TitleBar(CustomWindow *owner, QLabel **titleLabel)
      : QWidget(owner), owner_(owner) {
    setObjectName(QStringLiteral("customTitleBar"));
    setProperty("dragToRestoreEnabled", true);
    setFixedHeight(32);
    setAutoFillBackground(true);
    // Pull bar bg / text from the active theme — slightly darker than the
    // window so it reads as a distinct decoration band, but still light when
    // the light theme is active.
    const auto& tp = sli::toolkit::Theme::palette();
    auto pal = palette();
    pal.setColor(QPalette::Window, tp.window.darker(105));
    pal.setColor(QPalette::WindowText, tp.windowText);
    setPalette(pal);

    auto *layout = new QHBoxLayout(this);
    layout->setContentsMargins(10, 0, 0, 0);
    layout->setSpacing(0);

    *titleLabel = new QLabel(this);
    (*titleLabel)->setObjectName(QStringLiteral("customTitleLabel"));
    auto font = (*titleLabel)->font();
    font.setPointSizeF(font.pointSizeF() * 0.95);
    (*titleLabel)->setFont(font);
    layout->addWidget(*titleLabel);
    layout->addStretch();

    minBtn_ = makeButton(QStringLiteral("–"));   // en dash
    maxBtn_ = makeButton(QStringLiteral("□"));   // white square
    maxBtn_->setObjectName(QStringLiteral("customMaximizeButton"));
    closeBtn_ = makeButton(QStringLiteral("✕"),
                            QColor(220, 60, 60));
    layout->addWidget(minBtn_);
    layout->addWidget(maxBtn_);
    layout->addWidget(closeBtn_);

    connect(minBtn_, &QToolButton::clicked, owner_,
            &QWidget::showMinimized);
    connect(maxBtn_, &QToolButton::clicked, this, [this]() {
      toggleMaximized();
    });
    connect(closeBtn_, &QToolButton::clicked, owner_, &QWidget::close);

    addShortcut(QStringLiteral("customMinimizeShortcut"),
                QKeySequence(QStringLiteral("Alt+F9")),
                [this]() { owner_->showMinimized(); });
    addShortcut(QStringLiteral("customMaximizeShortcut"),
                QKeySequence(QStringLiteral("Alt+F10")),
                [this]() { toggleMaximized(); });
    addShortcut(QStringLiteral("customCloseShortcut"),
                QKeySequence(QStringLiteral("Alt+F4")),
                [this]() { owner_->close(); });

    syncWindowState(owner_->isMaximized());
  }

  void syncWindowState(bool maximized) {
    maxBtn_->setText(maximized ? QStringLiteral("❐") : QStringLiteral("□"));
    maxBtn_->setToolTip(maximized ? QStringLiteral("Restore")
                                  : QStringLiteral("Maximize"));
    maxBtn_->setAccessibleName(maxBtn_->toolTip());
    maxBtn_->setProperty("windowStateGlyph",
                         maximized ? QStringLiteral("restore")
                                   : QStringLiteral("maximize"));
  }

 protected:
  void mousePressEvent(QMouseEvent *e) override {
    if (e->button() != Qt::LeftButton) {
      QWidget::mousePressEvent(e);
      return;
    }
    pressGlobalPosition_ = e->globalPosition();
    dragPending_ = owner_->isMaximized();
    if (dragPending_) {
      e->accept();
      return;
    }
    if (auto *handle = owner_->windowHandle()) {
      handle->startSystemMove();
    }
    e->accept();
  }

  void mouseMoveEvent(QMouseEvent *e) override {
    if (!dragPending_ || !(e->buttons() & Qt::LeftButton)) {
      QWidget::mouseMoveEvent(e);
      return;
    }
    if ((e->globalPosition() - pressGlobalPosition_).manhattanLength() <
        QApplication::startDragDistance()) {
      e->accept();
      return;
    }

    dragPending_ = false;
    const qreal horizontalRatio =
        qBound(0.0, e->position().x() / qMax(1, width()), 1.0);
    owner_->showNormal();
    const QSize restoredSize = owner_->size();
    const QPoint restoredTopLeft(
        qRound(e->globalPosition().x() -
               horizontalRatio * restoredSize.width()),
        qRound(e->globalPosition().y() - e->position().y()));
    owner_->move(restoredTopLeft);
    if (auto *handle = owner_->windowHandle()) {
      handle->startSystemMove();
    }
    e->accept();
  }

  void mouseReleaseEvent(QMouseEvent *e) override {
    if (e->button() == Qt::LeftButton) {
      dragPending_ = false;
    }
    QWidget::mouseReleaseEvent(e);
  }

  void mouseDoubleClickEvent(QMouseEvent *e) override {
    if (e->button() != Qt::LeftButton) return;
    dragPending_ = false;
    toggleMaximized();
    e->accept();
  }

 private:
  QToolButton *makeButton(const QString &glyph,
                          QColor hoverBg = QColor(70, 70, 74)) {
    return new WindowControlButton(glyph, hoverBg, this);
  }

  void addShortcut(const QString &objectName, const QKeySequence &key,
                   const std::function<void()> &callback) {
    auto *shortcut = new QShortcut(key, owner_);
    shortcut->setObjectName(objectName);
    shortcut->setContext(Qt::WindowShortcut);
    connect(shortcut, &QShortcut::activated, owner_, callback);
  }

  void toggleMaximized() {
    if (owner_->isMaximized()) {
      owner_->showNormal();
    } else {
      owner_->showMaximized();
    }
  }

  CustomWindow *owner_;
  QToolButton *minBtn_ = nullptr;
  QToolButton *maxBtn_ = nullptr;
  QToolButton *closeBtn_ = nullptr;
  QPointF pressGlobalPosition_;
  bool dragPending_ = false;
};

}  // namespace

CustomWindow::CustomWindow(QWidget *parent) : QMainWindow(parent) {
  setWindowFlag(Qt::FramelessWindowHint, true);
  setMouseTracking(true);

  outerCentral_ = new QWidget(this);
  outerCentral_->setObjectName(QStringLiteral("customWindowOuter"));
  outerCentral_->setAutoFillBackground(true);
  outerCentral_->setMouseTracking(true);
  {
    // Use the theme's window colour for the frame around the body so a
    // theme switch propagates to the custom-decoration outer border.
    const QColor windowBg = sli::toolkit::Theme::palette().window;
    auto pal = outerCentral_->palette();
    pal.setColor(QPalette::Window, windowBg);
    outerCentral_->setPalette(pal);
  }
  outerLayout_ = new QVBoxLayout(outerCentral_);
  outerLayout_->setContentsMargins(resizeMargin_, resizeMargin_, resizeMargin_,
                                   resizeMargin_);
  outerLayout_->setSpacing(0);

  titleBar_ = new TitleBar(this, &titleLabel_);
  outerLayout_->addWidget(titleBar_);
  setMenuWidget(nullptr);
  setCentralWidget(outerCentral_);
}

void CustomWindow::setBody(QWidget *body) {
  if (body_ != nullptr) {
    outerLayout_->removeWidget(body_);
    body_->setParent(nullptr);
  }
  body_ = body;
  if (body_ != nullptr) {
    body_->setParent(outerCentral_);
    outerLayout_->addWidget(body_, 1);
  }
}

void CustomWindow::setTitleText(const QString &text) {
  setWindowTitle(text);
  if (titleLabel_ != nullptr) {
    titleLabel_->setText(text);
  }
}

bool CustomWindow::event(QEvent *e) {
  switch (e->type()) {
    case QEvent::MouseMove: {
      auto *me = static_cast<QMouseEvent *>(e);
      // Only react to "hover" moves (no buttons pressed). Press path
      // dispatches startSystemResize below.
      if (me->buttons() == Qt::NoButton && !isMaximized()) {
        updateCursorForEdges(detectEdges(me->position().toPoint()));
      }
      break;
    }
    case QEvent::MouseButtonPress: {
      auto *me = static_cast<QMouseEvent *>(e);
      if (me->button() == Qt::LeftButton && !isMaximized()) {
        const int edges = detectEdges(me->position().toPoint());
        if (edges != EdgeNone) {
          Qt::Edges qEdges;
          if (edges & EdgeLeft) qEdges |= Qt::LeftEdge;
          if (edges & EdgeRight) qEdges |= Qt::RightEdge;
          if (edges & EdgeTop) qEdges |= Qt::TopEdge;
          if (edges & EdgeBottom) qEdges |= Qt::BottomEdge;
          if (auto *handle = windowHandle()) {
            handle->startSystemResize(qEdges);
          }
          e->accept();
          return true;
        }
      }
      break;
    }
    case QEvent::WindowStateChange: {
      onStateChanged();
      break;
    }
    default:
      break;
  }
  return QMainWindow::event(e);
}

int CustomWindow::detectEdges(const QPoint &p) const {
  const int w = width();
  const int h = height();
  const int m = resizeMargin_;
  int edges = EdgeNone;
  if (p.x() <= m) edges |= EdgeLeft;
  if (p.x() >= w - m) edges |= EdgeRight;
  if (p.y() <= m) edges |= EdgeTop;
  if (p.y() >= h - m) edges |= EdgeBottom;
  return edges;
}

void CustomWindow::updateCursorForEdges(int edges) {
  switch (edges) {
    case EdgeLeft:
    case EdgeRight:
      setCursor(Qt::SizeHorCursor);
      break;
    case EdgeTop:
    case EdgeBottom:
      setCursor(Qt::SizeVerCursor);
      break;
    case EdgeTop | EdgeLeft:
    case EdgeBottom | EdgeRight:
      setCursor(Qt::SizeFDiagCursor);
      break;
    case EdgeTop | EdgeRight:
    case EdgeBottom | EdgeLeft:
      setCursor(Qt::SizeBDiagCursor);
      break;
    default:
      unsetCursor();
  }
}

void CustomWindow::onStateChanged() {
  // No resize margin when maximized — the compositor owns the geometry.
  const bool maximized = isMaximized();
  const int m = maximized ? 0 : resizeMargin_;
  outerLayout_->setContentsMargins(m, m, m, m);
  static_cast<TitleBar *>(titleBar_)->syncWindowState(maximized);
}

}  // namespace imgsli::app
