#pragma once

#include <QPropertyAnimation>
#include <QString>
#include <QWidget>

namespace sli::toolkit {

// Animated on/off toggle switch. Mirrors Python atomic/switch.py: track +
// knob with eased progress animation, hover halo, optional adjacent text
// label.
class Switch final : public QWidget {
  Q_OBJECT
  Q_PROPERTY(double progress READ progress WRITE setProgress)
  Q_PROPERTY(double hover READ hover WRITE setHover)

 public:
  static constexpr int kTrackWidth = 44;
  static constexpr int kTrackHeight = 22;
  static constexpr int kKnobDiameter = 12;
  static constexpr int kTextSpacing = 6;

  explicit Switch(QWidget* parent = nullptr);

  bool isChecked() const { return checked_; }
  void setChecked(bool checked);

  void setShowText(bool show);
  void setOnText(const QString& text);
  void setOffText(const QString& text);

  double progress() const { return progress_; }
  void setProgress(double p);
  double hover() const { return hover_; }
  void setHover(double h);

  QSize sizeHint() const override;

 signals:
  void checkedChanged(bool checked);
  void toggled(bool checked);

 protected:
  void paintEvent(QPaintEvent* event) override;
  void mousePressEvent(QMouseEvent* event) override;
  void keyPressEvent(QKeyEvent* event) override;
  void enterEvent(QEnterEvent* event) override;
  void leaveEvent(QEvent* event) override;

 private:
  void emitAnimateTo(double target);

  bool checked_ = false;
  bool showText_ = true;
  QString onText_;
  QString offText_;
  double progress_ = 0.0;
  double hover_ = 0.0;
  QPropertyAnimation animProgress_;
  QPropertyAnimation animHover_;
};

}  // namespace sli::toolkit
