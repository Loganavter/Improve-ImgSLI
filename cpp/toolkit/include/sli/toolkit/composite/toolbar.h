#pragma once

#include <QWidget>

class QHBoxLayout;

namespace sli::toolkit {

/// Rounded surface container for compact action/control rows.
class Toolbar final : public QWidget {
  Q_OBJECT

 public:
  explicit Toolbar(QWidget* parent = nullptr);

  void addWidget(QWidget* widget, int stretch = 0);
  void addSeparator();
  void addStretch(int stretch = 1);

 protected:
  void paintEvent(QPaintEvent* event) override;

 private:
  QHBoxLayout* layout_ = nullptr;
};

}  // namespace sli::toolkit
