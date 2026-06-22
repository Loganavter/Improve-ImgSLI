#include "sli/toolkit/composite/unified_flyout/model.h"

namespace sli::toolkit::unified_flyout {

FlyoutListModel::FlyoutListModel(QObject* parent)
    : QAbstractListModel(parent) {}

void FlyoutListModel::setItems(std::vector<FlyoutItem> items) {
  beginResetModel();
  items_ = std::move(items);
  if (currentIndex_ >= static_cast<int>(items_.size())) {
    currentIndex_ = -1;
  }
  endResetModel();
}

void FlyoutListModel::setCurrentIndex(int index) {
  if (index == currentIndex_) {
    return;
  }
  const int prev = currentIndex_;
  currentIndex_ = index;
  if (prev >= 0 && prev < static_cast<int>(items_.size())) {
    emit dataChanged(this->index(prev), this->index(prev), {kIsCurrentRole});
  }
  if (currentIndex_ >= 0 && currentIndex_ < static_cast<int>(items_.size())) {
    emit dataChanged(this->index(currentIndex_), this->index(currentIndex_),
                      {kIsCurrentRole});
  }
}

int FlyoutListModel::rowCount(const QModelIndex& parent) const {
  return parent.isValid() ? 0 : static_cast<int>(items_.size());
}

QVariant FlyoutListModel::data(const QModelIndex& index, int role) const {
  if (!index.isValid() || index.row() < 0 ||
      index.row() >= static_cast<int>(items_.size())) {
    return {};
  }
  const FlyoutItem& item = items_[index.row()];
  switch (role) {
    case Qt::DisplayRole:
    case kNameRole:
      return item.name;
    case kPathRole:
      return item.path;
    case kRatingRole:
      return item.rating;
    case kIndexRole:
      return index.row();
    case kIsCurrentRole:
      return index.row() == currentIndex_;
    case Qt::UserRole:
      return item.data;
  }
  return {};
}

bool FlyoutListModel::setData(const QModelIndex& index, const QVariant& value,
                              int role) {
  if (!index.isValid() || index.row() < 0 ||
      index.row() >= static_cast<int>(items_.size())) {
    return false;
  }
  FlyoutItem& item = items_[index.row()];
  switch (role) {
    case kNameRole:
      item.name = value.toString();
      break;
    case kRatingRole:
      item.rating = value.toInt();
      break;
    case kPathRole:
      item.path = value.toString();
      break;
    default:
      return false;
  }
  emit dataChanged(index, index, {role});
  return true;
}

Qt::ItemFlags FlyoutListModel::flags(const QModelIndex& index) const {
  if (!index.isValid()) {
    return Qt::NoItemFlags;
  }
  return Qt::ItemIsEnabled | Qt::ItemIsSelectable | Qt::ItemIsDragEnabled;
}

}  // namespace sli::toolkit::unified_flyout
