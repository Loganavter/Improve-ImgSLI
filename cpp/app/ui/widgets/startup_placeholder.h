#pragma once

#include <QColor>
#include <QPointer>
#include <QString>
#include <QWidget>

class QLabel;

namespace imgsli::app::ui::widgets {

// Transparent overlay shown over the image area before any image is loaded.
// Mirror of Python `src/ui/widgets/startup_placeholder.py`. Tracks the
// geometry of a target widget (typically the canvas) and centres a single
// label inside it.
class StartupPlaceholder : public QWidget {
  Q_OBJECT
 public:
  explicit StartupPlaceholder(QWidget* parent, QWidget* target = nullptr);

  void setTarget(QWidget* target);
  void setText(const QString& text);
  void setBackgroundColor(const QColor& color);

  // Re-applies the target widget geometry to this overlay and raises it on top.
  void syncGeometry();

 private:
  QPointer<QWidget> target_;
  QLabel* label_;
};

}  // namespace imgsli::app::ui::widgets
