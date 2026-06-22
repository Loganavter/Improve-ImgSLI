#pragma once

#include <QTimer>
#include <QWidget>

namespace sli::toolkit {

// Conic-gradient spinner driven by a 15ms timer; mirrors Python
// atomic/loading_spinner.py.
class LoadingSpinner final : public QWidget {
  Q_OBJECT

 public:
  explicit LoadingSpinner(QWidget* parent = nullptr);

  void start();
  void stop();
  bool isSpinning() const { return timer_.isActive(); }

 protected:
  void paintEvent(QPaintEvent* event) override;

 private slots:
  void tick();

 private:
  QTimer timer_;
  int angle_ = 0;
};

}  // namespace sli::toolkit
