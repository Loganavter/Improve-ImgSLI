#pragma once

#include <QAbstractButton>
#include <QColor>
#include <QIcon>
#include <QSize>
#include <QString>
#include <QVariant>

#include <memory>
#include <optional>
#include <utility>
#include <vector>

#include "sli/toolkit/buttons/specs.h"

namespace sli::toolkit::buttons {
class ButtonCapability;
}  // namespace sli::toolkit::buttons

namespace sli::toolkit::buttons {
class ButtonController;
class Painter;
}  // namespace sli::toolkit::buttons

namespace sli::toolkit {

class Button : public QAbstractButton {
  Q_OBJECT

 public:
  enum class Variant {
    Default,
    Surface,
    Ghost,
    Subtle,
  };

  explicit Button(const QString& text = {},
                  Variant variant = Variant::Surface,
                  QWidget* parent = nullptr);

  // Ergonomic builder mirroring Python's `Button(icon=…, toggle=…, …)`
  // keyword form. The C++ side reads the populated optional / nonempty fields
  // and produces an internal ButtonSpec + the matching capability set, so the
  // shell does not have to hand-assemble regions for the common one-region
  // case.
  struct Config {
    QString text;
    QIcon icon;
    QIcon iconChecked;          // optional alternate icon for checked state
    Variant variant = Variant::Surface;
    bool toggle = false;
    std::optional<QSize> size;
    std::optional<int> iconSize;
    QVariant badge;
    std::optional<std::pair<int, int>> scrollable;
    std::optional<int> longPressMs;     // any value enables long-press
    std::optional<std::vector<std::pair<QString, QVariant>>> menu;
    std::optional<bool> showUnderline;
    // Accent / red / theme-coloured paint. Mirrors Python's
    // `background_color=QColor(...)` keyword — drives the variant-aware
    // CustomPalette derivation in deriveCustomPalette(base, variant).
    std::optional<QColor> backgroundColor;
    // Mirrors Python's `corner_radius` — text buttons default to 2,
    // icon-only to 6.
    std::optional<int> cornerRadius;
    // Mirrors Python's `border_color=QColor(...)` — overrides the border
    // color from theme tokens.
    std::optional<QColor> borderColor;
    // Mirrors Python's `density` property — "normal" | "compact".
    QString density = QStringLiteral("normal");
    // Mirrors Python's `wheel_requires_focus` — when false, wheel scrolls
    // without the widget having focus.
    bool wheelRequiresFocus = false;
    // Mirrors Python's `defer_click` — when true, click handling is
    // deferred to the caller.
    bool deferClick = false;
  };

  explicit Button(const Config& config, QWidget* parent = nullptr);
  ~Button() override;

  QSize sizeHint() const override;
  void setVariant(Variant variant);
  Variant variant() const { return variant_; }

  void setSpec(buttons::ButtonSpec spec);
  const buttons::ButtonSpec& spec() const;

  // Python's `setChecked` is gated on `_has_toggle` — override to match.
  void setChecked(bool checked);

  // Override the default ripple overlay with explicit colors. Mirrors
  // Python's `setRippleColors(from_color, to_color)`. With both unset
  // RippleLayer paints the default theme overlay.
  void setRippleColors(QColor colorFrom, QColor colorTo);
  void clearRippleColors();

  // Attach a capability (LongPress/Menu/Scroll). Ownership transferred to the
  // Button; capability's QObject parent is reset to this widget so it is
  // destroyed with the button.
  void addCapability(std::unique_ptr<buttons::ButtonCapability> capability,
                     const QString& regionId = QStringLiteral("_main"));

  // Scroll value API — mirrors Python's setValue/getValue/setRange.
  void setValue(int val);
  int value() const { return scrollValue_; }
  void setRange(int minV, int maxV);

  // Mirrors Python `Button.setIconSizePx(size_px)`. Overrides the icon size
  // on the `_main` region without changing any other layout property. The
  // Python side sets the `iconSizePx` dynamic property AND triggers a
  // geometry update; here we mutate the spec directly which has the same
  // effect (next paintEvent re-queries the region draw context).
  void setIconSizePx(int sizePx);

 signals:
  void regionClicked(const QString& regionId);
  void regionPressed(const QString& regionId);
  void regionReleased(const QString& regionId);
  void longPressed(const QString& regionId);
  void menuTriggered(const QString& regionId, const QVariant& data);

  // Mirrors Python's per-button signals (non-region).
  void pressed();
  void released();
  void rightClicked();
  void middleClicked();
  void valueChanged(int value);

 protected:
  void paintEvent(QPaintEvent* event) override;
  void resizeEvent(QResizeEvent* event) override;
  void mousePressEvent(QMouseEvent* event) override;
  void mouseReleaseEvent(QMouseEvent* event) override;
  void mouseMoveEvent(QMouseEvent* event) override;
  void wheelEvent(QWheelEvent* event) override;
  void enterEvent(QEnterEvent* event) override;
  void leaveEvent(QEvent* event) override;
  void keyPressEvent(QKeyEvent* event) override;

 private:
  static QString variantName(Variant variant);
  buttons::ButtonSpec buildSimpleSpec(const QString& text,
                                       Variant variant) const;

  Variant variant_;
  std::unique_ptr<buttons::ButtonController> controller_;
  std::optional<QString> hoveredRegion_;
  std::optional<QString> pressedRegion_;
  std::vector<std::unique_ptr<buttons::ButtonCapability>> capabilities_;
  std::optional<QColor> rippleColorFrom_;
  std::optional<QColor> rippleColorTo_;
  int scrollValue_ = 0;
  int scrollMin_ = 0;
  int scrollMax_ = 0;
  std::optional<int> savedScrollValue_;
  bool hasToggle_ = false;
};

}  // namespace sli::toolkit
