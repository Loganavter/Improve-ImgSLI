#pragma once

#include <QPointer>
#include <QWidget>

class QVBoxLayout;

namespace sli::toolkit {

/// In-window anchored flyout. Only one Flyout is visible at a time.
class Flyout : public QWidget {
  Q_OBJECT

 public:
  explicit Flyout(QWidget* parent);
  ~Flyout() override;

  void addWidget(QWidget* widget);
  void showAligned(QWidget* anchor,
                   const QString& anchorPoint = QStringLiteral("bottom-center"),
                   const QString& flyoutPoint = QStringLiteral("top-center"),
                   int offset = 5);
  QWidget* anchorWidget() const { return anchor_; }

 signals:
  void opened();
  void closed();

 protected:
  bool eventFilter(QObject* watched, QEvent* event) override;
  void keyPressEvent(QKeyEvent* event) override;
  void paintEvent(QPaintEvent* event) override;
  void hideEvent(QHideEvent* event) override;

 private:
  static QPoint alignedPoint(const QRect& rect, const QString& spec);
  bool containsGlobal(const QPoint& point) const;

 protected:
  QVBoxLayout* contentLayout_ = nullptr;

 private:
  QPointer<QWidget> anchor_;
  QPointer<QWidget> host_;
  bool eventFilterInstalled_ = false;
  static QPointer<Flyout> activeFlyout_;
};

}  // namespace sli::toolkit
