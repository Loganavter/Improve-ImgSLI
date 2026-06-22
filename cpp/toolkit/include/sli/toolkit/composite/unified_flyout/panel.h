#pragma once

#include <QWidget>

#include <memory>

#include "sli/toolkit/composite/unified_flyout/common.h"
#include "sli/toolkit/composite/unified_flyout/model.h"
#include "sli/toolkit/composite/unified_flyout/style.h"

namespace sli::toolkit::unified_flyout {

class ItemDelegate;
class OverlayListView;
class RoundedClipEffect;

class Panel : public QWidget {
  Q_OBJECT

 public:
  explicit Panel(QWidget* parent = nullptr);
  ~Panel() override;

  void setMode(FlyoutMode mode);
  FlyoutMode mode() const { return mode_; }
  void setStyle(const FlyoutStyle& style);

  FlyoutListModel* model() { return model_; }
  void setItems(std::vector<FlyoutItem> items);
  void setCurrentIndex(int index);
  int currentIndex() const;

  void showForAnchor(QWidget* anchor);

 signals:
  void itemActivated(int index);
  void closed();

 protected:
  void paintEvent(QPaintEvent* event) override;
  void resizeEvent(QResizeEvent* event) override;
  void hideEvent(QHideEvent* event) override;
  void closeEvent(QCloseEvent* event) override;

 private slots:
  void onIndexClicked(const QModelIndex& index);

 private:
  void applyStyle();
  void applyContainerGeometry();
  void drawShadow(QPainter* painter, const QRectF& rect, int steps);

  FlyoutMode mode_ = FlyoutMode::SingleLeft;
  FlyoutStyle style_ = defaultStyle();
  FlyoutListModel* model_ = nullptr;
  ItemDelegate* delegate_ = nullptr;
  OverlayListView* view_ = nullptr;
  std::unique_ptr<RoundedClipEffect> clipEffect_;
  QWidget* container_ = nullptr;
};

}  // namespace sli::toolkit::unified_flyout