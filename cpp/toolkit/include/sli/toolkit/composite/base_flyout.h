#pragma once
#ifndef SLI_TOOLKIT_COMPOSITE_BASE_FLYOUT_H
#define SLI_TOOLKIT_COMPOSITE_BASE_FLYOUT_H

#include <QEasingCurve>
#include <QList>
#include <QPair>
#include <QPointer>
#include <QString>
#include <QVariant>
#include <QWidget>

class QButtonGroup;
class QColor;
class QHBoxLayout;
class QPropertyAnimation;
class QVBoxLayout;

namespace sli::toolkit {

class ColorSwatch;
class Label;
class RadioButton;

/// Base class for anchored in-window flyout panels.
/// Mirrors Python's BaseFlyout from
///   sli_ui_toolkit/ui/widgets/composite/base_flyout.py
///
/// Provides:
///   - Shadow + content surface setup (SHADOW_RADIUS=8, CONTENT_RADIUS=8)
///   - Anchor-aligned positioning with optional slide animation
///   - Builder helpers: addWidget, addSection, addRow, addRadioRow,
///     makeColorSwatch
///   - FlyoutManager integration (singleton hide-other-on-show)
///   - Theme-change re-style
class BaseFlyout : public QWidget {
  Q_OBJECT

 public:
  static constexpr int SHADOW_RADIUS = 8;
  static constexpr int CONTENT_RADIUS = 8;

  explicit BaseFlyout(QWidget* parent);
  ~BaseFlyout() override;

  // --- builder helpers ---

  void addWidget(QWidget* widget);

  /// Add a bold section-heading label (pixel_size=12, color_token="dialog.text").
  Label* addSection(const QString& text, int pixelSize = 12);

  /// Add a labeled row: label left, widget right.
  /// label_pixel_size=11, stretch_before_widget=true by default.
  Label* addRow(const QString& labelText, QWidget* widget,
                int labelPixelSize = 11,
                bool stretchBeforeWidget = true);

  /// Add a label followed by a horizontal row of RadioButtons.
  /// options: list of (displayText, value) pairs.
  /// default: QVariant — if invalid, first radio is checked;
  ///          otherwise the radio whose value equals default is checked.
  Label* addRadioRow(const QString& labelText,
                     const QList<QPair<QString, QVariant>>& options,
                     QButtonGroup* group,
                     const QVariant& defaultValue = QVariant());

  /// Build a round color-picker swatch (size=28, alpha=true).
  ColorSwatch* makeColorSwatch(const QColor& color = QColor(255, 255, 255),
                               int size = 28,
                               bool alpha = true);

  // --- positioning ---

  /// Align a point on the flyout to a point on anchorWidget.
  ///
  /// anchorPoint / flyoutPoint: strings like "bottom-center", "top-left",
  /// "center-right".  Single token treated as other axis = center.
  ///
  /// position: legacy compat string ("top","bottom","left","right", corners).
  ///           Empty string means "use anchorPoint/flyoutPoint".
  ///
  /// animation: "none" (default) or "slide".
  /// animationDurationMs: overrides config default (160 ms) when >= 0.
  /// animationDistance: pixels for slide start offset (24).
  void showAligned(QWidget* anchorWidget,
                   const QString& anchorPoint = QStringLiteral("bottom-center"),
                   const QString& flyoutPoint = QStringLiteral("top-center"),
                   const QString& position = QString(),
                   int offset = 5,
                   const QString& animation = QStringLiteral("none"),
                   int animationDurationMs = -1,
                   int animationDistance = 24,
                   QEasingCurve::Type easing = QEasingCurve::OutQuad);

  bool containsGlobal(const QPoint& globalPos) const;
  bool anchorContainsGlobal(const QPoint& globalPos) const;

  QWidget* anchorWidget() const { return anchorWidget_; }

  // Widget tuple for FlyoutManager anchor tracking.
  QList<QWidget*> anchorWidgets() const;

 public slots:
  void hide();
  void show();

 protected:
  void keyPressEvent(QKeyEvent* event) override;
  void paintEvent(QPaintEvent* event) override;

 private:
  void applyBaseStyle();
  void ensureOverlayParent(QWidget* anchorWidget);

  QRect overlayRectRelativeToAnchor(QWidget* anchorWidget,
                                    const QSize& size,
                                    const QString& position,
                                    int offset) const;

  // --- in_window_surface helpers (inlined) ---

  /// Compute the anchor rect in parent-widget coordinates.
  QRect surfaceAnchorRect(QWidget* anchor) const;

  /// Compute the available rect for placement (parent rect or screen).
  QRect surfaceAvailableRect(QWidget* anchor, int margin = 0) const;

  /// Clamp rect to stay within available.
  static QRect clampSurfaceRect(const QRect& rect, const QRect& available);

  /// Place rect relative to anchor using legacy position string.
  QRect placeSurfaceRect(QWidget* anchor,
                         const QSize& size,
                         const QString& position,
                         int offset,
                         int margin = 0) const;

  // --- _parse_point / _point_in_rect helpers ---

  /// Parse "bottom-left", "top", etc. → (fx, fy) fractions in [0,1].
  static std::pair<double, double> parsePoint(const QString& spec);

  /// Map a fraction point to integer pixel coordinates within rect.
  static QPoint pointInRect(const QRect& rect, const QString& spec);

  // --- animation ---
  void onShowAnimationFinished();

  // --- FlyoutManager (inline singleton) ---
  void registerWithManager();
  void unregisterFromManager();
  void requestShow();
  void requestHide();

  // members
  QWidget* overlayLayer_ = nullptr;        // resolved in-window overlay widget
  QPointer<QWidget> anchorWidget_;         // last anchor passed to showAligned

  QVBoxLayout* mainLayout_ = nullptr;
  QWidget* container_ = nullptr;           // "FlyoutContainer" shadow surface
  QVBoxLayout* contentLayout_ = nullptr;

  QPropertyAnimation* showAnimation_ = nullptr;

  // FlyoutManager singleton state (mirrors Python FlyoutManager)
  static QPointer<BaseFlyout> activeFlyout_;
};

}  // namespace sli::toolkit

#endif  // SLI_TOOLKIT_COMPOSITE_BASE_FLYOUT_H
