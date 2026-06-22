#pragma once

#include <QFont>
#include <QPointer>
#include <QPropertyAnimation>
#include <QScrollArea>
#include <QString>
#include <QStringList>
#include <QVBoxLayout>
#include <QWidget>

#include <chrono>
#include <optional>
#include <vector>

#include "sli/toolkit/composite/flyout.h"

class QHideEvent;

namespace sli::toolkit {

/// Scrollable list-of-options flyout with rows, current-item indicator,
/// drop-in animation, and screen-edge clamping.
/// Mirrors Python's SimpleOptionsFlyout.
class SimpleOptionsFlyout : public Flyout {
  Q_OBJECT

 public:
  static constexpr int kMargin = 8;
  static constexpr int kAppearExtraY = 6;
  static constexpr int kMaxVisibleItems = 12;
  static constexpr int kWindowMargin = 8;

  explicit SimpleOptionsFlyout(QWidget* parentWidget = nullptr);

  void setMaxVisibleItems(int n);
  void setRowHeight(int h);
  void setRowFont(const QFont& f);

  void populate(const QStringList& labels, int currentIndex = -1);

  void showBelow(QWidget* anchorWidget, bool exactWidthMatch = true);

 signals:
  void itemChosen(int index);
  void closed();

 public slots:
  void hide();

 protected:
  void hideEvent(QHideEvent* event) override;

 private:
  void updateSize(int matchWidth = 0,
                  bool exactMatch = false,
                  std::optional<int> availableHeight = std::nullopt);
  void ensureOverlayParent(QWidget* anchor);
  void onRowClicked(int idx);
  void onAnimationFinished();

  // Internal row widget — mirrors Python _SimpleRow
  QWidget* createRow(int index,
                     const QString& text,
                     bool isCurrent,
                     int itemHeight,
                     const QFont& itemFont);

  QWidget* parentWidget_ = nullptr;
  QStringList options_;
  int currentIndex_ = -1;
  int itemHeight_ = 36;
  QFont itemFont_;
  int maxVisibleItems_ = kMaxVisibleItems;
  int moveDurationMs_ = 150;  // default flyout_animation_duration_ms
  int dropOffsetPx_ = 80;

  QPointer<QPropertyAnimation> anim_;
  QPointer<QWidget> anchorWidget_;

  QScrollArea* scrollArea_ = nullptr;
  QWidget* rowsContainer_ = nullptr;
  QVBoxLayout* rowsLayout_ = nullptr;
  std::vector<QWidget*> rowWidgets_;

  bool justOpened_ = false;
  std::chrono::steady_clock::time_point openTimestamp_;
};

}  // namespace sli::toolkit