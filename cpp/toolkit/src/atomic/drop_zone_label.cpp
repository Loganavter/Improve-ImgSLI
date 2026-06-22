#include "sli/toolkit/atomic/drop_zone_label.h"

#include <QColor>
#include <QDragEnterEvent>
#include <QDragLeaveEvent>
#include <QDropEvent>
#include <QMimeData>
#include <QPainter>
#include <QPaintEvent>
#include <QPen>
#include <QRectF>
#include <QUrl>
#include <Qt>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

DropZoneLabel::DropZoneLabel(const QString& promptText, QWidget* parent)
    : QWidget(parent), prompt_(promptText) {
  setAcceptDrops(true);
  setMinimumHeight(80);
}

void DropZoneLabel::setPromptText(const QString& text) {
  prompt_ = text;
  update();
}

void DropZoneLabel::paintEvent(QPaintEvent*) {
  QPainter p(this);
  p.setRenderHint(QPainter::Antialiasing);
  const Palette& palette = Theme::palette();
  const QColor border = dragHovered_ ? palette.accent : palette.border;
  QPen pen(border);
  pen.setWidth(dragHovered_ ? 2 : 1);
  pen.setStyle(Qt::DashLine);
  pen.setDashPattern({4, 4});
  p.setPen(pen);
  if (dragHovered_) {
    QColor fill = palette.accent;
    fill.setAlphaF(0.08);
    p.setBrush(fill);
  } else {
    p.setBrush(palette.base);
  }
  const QRectF r = QRectF(rect()).adjusted(2, 2, -2, -2);
  p.drawRoundedRect(r, 8, 8);
  p.setPen(palette.windowText);
  p.drawText(r, Qt::AlignCenter | Qt::TextWordWrap, prompt_);
}

void DropZoneLabel::dragEnterEvent(QDragEnterEvent* event) {
  if (event->mimeData()->hasUrls()) {
    dragHovered_ = true;
    event->acceptProposedAction();
    update();
  }
}

void DropZoneLabel::dragLeaveEvent(QDragLeaveEvent*) {
  dragHovered_ = false;
  update();
}

void DropZoneLabel::dropEvent(QDropEvent* event) {
  QStringList paths;
  for (const QUrl& url : event->mimeData()->urls()) {
    if (url.isLocalFile()) {
      paths.append(url.toLocalFile());
    }
  }
  dragHovered_ = false;
  update();
  if (!paths.isEmpty()) {
    emit filesDropped(paths);
    event->acceptProposedAction();
  }
}

}  // namespace sli::toolkit
