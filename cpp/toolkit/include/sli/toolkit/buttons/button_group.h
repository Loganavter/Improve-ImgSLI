#pragma once

#include <QString>
#include <QWidget>

#include <vector>

class QHBoxLayout;

namespace sli::toolkit {

class ButtonGroup : public QWidget {
  Q_OBJECT

 public:
  explicit ButtonGroup(std::vector<QWidget*> buttons = {},
                       const QString& label = {}, QWidget* parent = nullptr);

  void setLabel(const QString& text);
  QString label() const { return label_; }

  void addButton(QWidget* button);

 protected:
  void paintEvent(QPaintEvent* event) override;

 private:
  QString label_;
  int borderWidth_ = 1;
  int borderRadius_ = 8;
  QHBoxLayout* layout_ = nullptr;
};

}  // namespace sli::toolkit
