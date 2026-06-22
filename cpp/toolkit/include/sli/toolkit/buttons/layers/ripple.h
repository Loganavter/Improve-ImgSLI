#pragma once

#include <QColor>
#include <QObject>
#include <QPointF>
#include <QTimer>

#include <optional>

class QWidget;

namespace sli::toolkit::buttons {

class RippleEffect : public QObject {
  Q_OBJECT

 public:
  static constexpr int kDurationMs = 280;
  static constexpr int kTickMs = 16;
  static constexpr int kPeakAlphaLight = 31;
  static constexpr int kPeakAlphaDark = 41;

  explicit RippleEffect(QWidget* widget);

  void trigger(const QPointF& origin,
               std::optional<QColor> colorFrom = std::nullopt,
               std::optional<QColor> colorTo = std::nullopt);

  bool isActive() const { return center_.has_value(); }
  std::optional<QPointF> center() const { return center_; }
  std::optional<QColor> colorFrom() const { return colorFrom_; }
  std::optional<QColor> colorTo() const { return colorTo_; }
  double progress() const;

  QWidget* widget() const { return widget_; }

 private slots:
  void onTick();

 private:
  QWidget* widget_ = nullptr;
  QTimer timer_;
  int elapsedMs_ = 0;
  std::optional<QPointF> center_;
  std::optional<QColor> colorFrom_;
  std::optional<QColor> colorTo_;
};

}  // namespace sli::toolkit::buttons
