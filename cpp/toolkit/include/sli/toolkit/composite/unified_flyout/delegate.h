#pragma once

#include <QPoint>
#include <QPointF>
#include <QStyledItemDelegate>
#include <QTimer>

namespace sli::toolkit::unified_flyout {

class ItemDelegate : public QStyledItemDelegate {
  Q_OBJECT

 public:
  explicit ItemDelegate(QObject* parent = nullptr);

  void paint(QPainter* painter, const QStyleOptionViewItem& option,
             const QModelIndex& index) const override;
  QSize sizeHint(const QStyleOptionViewItem& option,
                 const QModelIndex& index) const override;

  void setItemHeight(int height) { itemHeight_ = height; }
  void setItemType(const QString& itemType) { itemType_ = itemType; }

 protected:
  bool editorEvent(QEvent* event, QAbstractItemModel* model,
                   const QStyleOptionViewItem& option,
                   const QModelIndex& index) override;
  bool helpEvent(QHelpEvent* event, QAbstractItemView* view,
                 const QStyleOptionViewItem& option,
                 const QModelIndex& index) override;

 private:
  void paintRating(QPainter* p, const QRect& r, int rating,
                   const QFont& itemFont) const;
  void paintSimple(QPainter* p, const QRect& r, const QString& name,
                   const QFont& itemFont) const;

  int itemHeight_ = 36;

  // Layout constants (mirror Python).
  static constexpr int kRatingWidth = 25;
  static constexpr int kBtnSize = 22;
  static constexpr int kSpacing = 6;
  static constexpr int kMargin = 2;

  QString itemType_ = QStringLiteral("image");
};

}  // namespace sli::toolkit::unified_flyout