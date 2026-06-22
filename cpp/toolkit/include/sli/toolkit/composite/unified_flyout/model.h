#pragma once

#include <QAbstractListModel>
#include <QString>
#include <QVariant>
#include <Qt>

#include <vector>

namespace sli::toolkit::unified_flyout {

constexpr int kNameRole = Qt::UserRole + 1;
constexpr int kRatingRole = Qt::UserRole + 2;
constexpr int kPathRole = Qt::UserRole + 3;
constexpr int kIndexRole = Qt::UserRole + 4;
constexpr int kIsCurrentRole = Qt::UserRole + 5;

struct FlyoutItem {
  QString name;
  QString path;
  int rating = 0;
  QVariant data;
};

class FlyoutListModel : public QAbstractListModel {
  Q_OBJECT

 public:
  explicit FlyoutListModel(QObject* parent = nullptr);

  void setItems(std::vector<FlyoutItem> items);
  void setCurrentIndex(int index);
  int currentIndex() const { return currentIndex_; }
  const std::vector<FlyoutItem>& items() const { return items_; }

  int rowCount(const QModelIndex& parent = {}) const override;
  QVariant data(const QModelIndex& index,
                int role = Qt::DisplayRole) const override;
  bool setData(const QModelIndex& index, const QVariant& value,
               int role = Qt::EditRole) override;
  Qt::ItemFlags flags(const QModelIndex& index) const override;

 private:
  std::vector<FlyoutItem> items_;
  int currentIndex_ = -1;
};

}  // namespace sli::toolkit::unified_flyout
