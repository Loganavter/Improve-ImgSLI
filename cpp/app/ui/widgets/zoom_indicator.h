#pragma once

#include "ui/widgets/rounded_overlay.h"

#include <QPointer>
#include <QString>
#include <functional>

class QLabel;
class QPushButton;

namespace imgsli::app::ui::widgets {

// Overlay showing current zoom percent + a reset button. Mirror of Python
// `src/ui/widgets/zoom_indicator.py`. Self-contained: takes a callable that
// returns the current i18n prefix and a target widget whose top-right corner
// it tracks. The owner is responsible for wiring `resetButton()->clicked`.
class ZoomIndicator : public RoundedOverlayWidget {
  Q_OBJECT
 public:
  using PrefixProvider = std::function<QString()>;

  explicit ZoomIndicator(QWidget* parent, PrefixProvider prefixProvider,
                         QWidget* target = nullptr);

  void setTarget(QWidget* target);
  QPushButton* resetButton() const { return resetButton_; }

  // Updates the percent label and (re-)evaluates visibility. The widget is
  // shown only when zoom is meaningfully different from 1.0 *or* a pan is
  // active.
  void updateZoom(double zoom, double panX = 0.0, double panY = 0.0);

  // Aligns the indicator to the top-right corner of the target widget.
  void syncPosition();

 private:
  PrefixProvider prefixProvider_;
  QPointer<QWidget> target_;
  QLabel* label_;
  QPushButton* resetButton_;
};

}  // namespace imgsli::app::ui::widgets
