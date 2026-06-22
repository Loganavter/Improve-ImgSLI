#include "sli/toolkit/composite/unified_flyout/delegate.h"

#include <QAbstractItemView>
#include <QApplication>
#include <QFont>
#include <QFontMetrics>
#include <QHelpEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QPen>
#include <QRect>

#include "sli/toolkit/composite/unified_flyout/model.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit::unified_flyout {

ItemDelegate::ItemDelegate(QObject* parent) : QStyledItemDelegate(parent) {}

void ItemDelegate::paint(QPainter* painter,
                         const QStyleOptionViewItem& option,
                         const QModelIndex& index) const {
  painter->save();
  painter->setRenderHint(QPainter::Antialiasing);

  const QString name =
      index.data(kNameRole).toString().isEmpty()
          ? QStringLiteral("-----")
          : index.data(kNameRole).toString();
  const int rating = index.data(kRatingRole).toInt();
  const bool isCurrent = index.data(kIsCurrentRole).toBool();
  const QString fullPath = index.data(kPathRole).toString();

  const QRect r = option.rect;

  // Background — rounded rect with theme tokens (Python lines 90-101).
  const bool underMouse = option.state & QStyle::State_MouseOver;
  const QColor hoverBg =
      Theme::getColor(QStringLiteral("list_item.background.hover"));
  const QColor normalBg =
      Theme::getColor(QStringLiteral("list_item.background.normal"));
  const QColor bgColor =
      (isCurrent || underMouse) ? hoverBg : normalBg;
  painter->setPen(Qt::NoPen);
  painter->setBrush(bgColor);
  const QRect bgRect =
      r.adjusted(kMargin, kMargin, -kMargin, -kMargin);
  painter->drawRoundedRect(bgRect, 5, 5);

  // Accent indicator — 3px round-cap line on the left for current (Python 103-110).
  if (isCurrent) {
    const QColor accent = Theme::getColor(QStringLiteral("accent"));
    QPen accentPen(accent);
    accentPen.setWidth(3);
    accentPen.setCapStyle(Qt::RoundCap);
    painter->setPen(accentPen);
    const int y1 = r.top() + 7;
    const int y2 = r.bottom() - 7;
    const int x = r.left() + accentPen.width();
    painter->drawLine(x, y1, x, y2);
  }

  QFont itemFont = option.font;

  if (itemType_ == QStringLiteral("image")) {
    paintRating(painter, r, rating, itemFont);

    // Separator between rating and name.
    const int xSep = r.left() + kMargin + kRatingWidth + kSpacing / 2;
    const QColor separator =
        Theme::getColor(QStringLiteral("separator.color"));
    painter->setPen(QPen(separator, 1));
    painter->drawLine(xSep, r.top() + 6, xSep, r.bottom() - 6);

    // Name.
    const int nameX = r.left() + kMargin + kRatingWidth + kSpacing;
    const int nameWidth =
        r.width() - nameX - (kBtnSize * 2) - (kSpacing * 2) - kMargin;
    const QRect nameRect(nameX, r.top(), std::max(0, nameWidth), r.height());
    painter->setFont(itemFont);
    painter->setPen(Theme::getColor(QStringLiteral("list_item.text.normal")));

    QFontMetrics fm(itemFont);
    const QString elided =
        fm.elidedText(name, Qt::ElideRight, nameWidth);
    painter->drawText(nameRect, Qt::AlignVCenter | Qt::AlignLeft, elided);

    // +/- buttons.
    const int btnY = r.top() + (r.height() - kBtnSize) / 2;
    const int btnMinusX =
        r.right() - (kBtnSize * 2) - kSpacing - kMargin;
    const int btnPlusX = r.right() - kBtnSize - kMargin;
    constexpr int kIconSize = 9;

    // Draw minus icon (simple circle with line).
    const QRect minusRect(btnMinusX + (kBtnSize - kIconSize) / 2,
                          btnY + (kBtnSize - kIconSize) / 2, kIconSize,
                          kIconSize);
    painter->setPen(QPen(Theme::getColor(QStringLiteral("dialog.text")), 1.2));
    painter->setBrush(Qt::NoBrush);
    painter->drawEllipse(minusRect.adjusted(1, 1, -1, -1));
    painter->drawLine(minusRect.left() + 3, minusRect.center().y(),
                      minusRect.right() - 3, minusRect.center().y());

    // Draw plus icon.
    const QRect plusRect(btnPlusX + (kBtnSize - kIconSize) / 2,
                         btnY + (kBtnSize - kIconSize) / 2, kIconSize,
                         kIconSize);
    painter->setPen(QPen(Theme::getColor(QStringLiteral("dialog.text")), 1.2));
    painter->setBrush(Qt::NoBrush);
    painter->drawEllipse(plusRect.adjusted(1, 1, -1, -1));
    const int cx = plusRect.center().x();
    const int cy = plusRect.center().y();
    painter->drawLine(cx, plusRect.top() + 3, cx, plusRect.bottom() - 3);
    painter->drawLine(plusRect.left() + 3, cy, plusRect.right() - 3, cy);
  } else {
    paintSimple(painter, r, name, itemFont);
  }

  painter->restore();
}

void ItemDelegate::paintRating(QPainter* p, const QRect& r, int rating,
                               const QFont& itemFont) const {
  const QRect ratingRect(r.left() + kMargin, r.top(), kRatingWidth,
                         r.height());
  QFont ratingFont(itemFont);
  const int basePx = itemFont.pixelSize() > 0 ? itemFont.pixelSize()
                                               : QFontMetrics(itemFont).height();
  ratingFont.setPixelSize(std::max(8, basePx - 3));
  p->setFont(ratingFont);
  p->setPen(Theme::getColor(QStringLiteral("list_item.text.rating")));
  p->drawText(ratingRect, Qt::AlignCenter, QString::number(rating));
}

void ItemDelegate::paintSimple(QPainter* p, const QRect& r,
                               const QString& name,
                               const QFont& itemFont) const {
  const int nameWidth = r.width() - (kMargin * 2);
  const QRect nameRect(r.left() + kMargin, r.top(), std::max(0, nameWidth),
                       r.height());
  p->setFont(itemFont);
  p->setPen(Theme::getColor(QStringLiteral("list_item.text.normal")));
  QFontMetrics fm(itemFont);
  const QString elided = fm.elidedText(name, Qt::ElideRight, nameWidth);
  p->drawText(nameRect, Qt::AlignVCenter | Qt::AlignLeft, elided);
}

QSize ItemDelegate::sizeHint(const QStyleOptionViewItem& option,
                              const QModelIndex& index) const {
  QSize s = QStyledItemDelegate::sizeHint(option, index);
  s.setHeight(itemHeight_);
  return s;
}

bool ItemDelegate::editorEvent(QEvent* event, QAbstractItemModel* model,
                                const QStyleOptionViewItem& option,
                                const QModelIndex& index) {
  if (itemType_ != QStringLiteral("image")) {
    return QStyledItemDelegate::editorEvent(event, model, option, index);
  }

  const QRect r = option.rect;
  const int btnY = r.top() + (r.height() - kBtnSize) / 2;
  const int btnMinusX =
      r.right() - (kBtnSize * 2) - kSpacing - kMargin;
  const int btnPlusX = r.right() - kBtnSize - kMargin;
  const QRect btnMinusRect(btnMinusX, btnY, kBtnSize, kBtnSize);
  const QRect btnPlusRect(btnPlusX, btnY, kBtnSize, kBtnSize);

  auto* mouseEvent = dynamic_cast<QMouseEvent*>(event);
  if (mouseEvent == nullptr) {
    return QStyledItemDelegate::editorEvent(event, model, option, index);
  }

  if (mouseEvent->type() == QEvent::MouseButtonPress &&
      mouseEvent->button() == Qt::LeftButton) {
    const QPoint clickPos = mouseEvent->pos();

    if (btnPlusRect.contains(clickPos)) {
      // Increment rating — Python emits through gesture transaction.
      model->setData(index, index.data(kRatingRole).toInt() + 1,
                     kRatingRole);
      emit commitData(nullptr);  // notify view
      return true;
    }
    if (btnMinusRect.contains(clickPos)) {
      const int newRating =
          std::max(0, index.data(kRatingRole).toInt() - 1);
      model->setData(index, newRating, kRatingRole);
      emit commitData(nullptr);
      return true;
    }
  }

  return QStyledItemDelegate::editorEvent(event, model, option, index);
}

bool ItemDelegate::helpEvent(QHelpEvent* event, QAbstractItemView* view,
                              const QStyleOptionViewItem& option,
                              const QModelIndex& index) {
  if (event->type() == QEvent::ToolTip) {
    const QString path = index.data(kPathRole).toString();
    if (!path.isEmpty()) {
      // Python shows a PathTooltip — we set the tooltip directly.
      view->setToolTip(path);
    }
    return true;
  }
  return QStyledItemDelegate::helpEvent(event, view, option, index);
}

}  // namespace sli::toolkit::unified_flyout