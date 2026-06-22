#include "sli/toolkit/atomic/group_box.h"

#include <QFont>
#include <QFontMetrics>
#include <QLayout>
#include <QPainter>
#include <QVBoxLayout>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

GroupBox::GroupBox(const QString& title, QWidget* parent)
    : QWidget(parent),
      title_(title),
      content_(new QVBoxLayout(this)) {
    setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Preferred);
    content_->setSpacing(8);
    updateContentMargins();
}

void GroupBox::setTitle(const QString& title) {
    if (title_ == title) {
        return;
    }
    title_ = title;
    updateContentMargins();
    updateGeometry();
    update();
}

void GroupBox::addWidget(QWidget* widget) {
    content_->addWidget(widget);
}

void GroupBox::addLayout(QLayout* layout) {
    content_->addLayout(layout);
}

void GroupBox::updateContentMargins() {
    int titleH = 0;
    if (!title_.isEmpty()) {
        QFont f = font();
        f.setBold(true);
        titleH = QFontMetrics(f).height();
    }
    const int topMargin = static_cast<int>(titleH * 0.8) + 12;
    content_->setContentsMargins(12, topMargin, 12, 12);
}

QSize GroupBox::sizeHint() const {
    QSize body = content_->sizeHint();
    int titleW = 0;
    if (!title_.isEmpty()) {
        QFont f = font();
        f.setBold(true);
        titleW = QFontMetrics(f).horizontalAdvance(title_);
    }
    const int titleFull = kTitleLeftPad + titleW + 30;
    return {qMax(body.width(), titleFull), body.height()};
}

QSize GroupBox::minimumSizeHint() const {
    return sizeHint();
}

void GroupBox::paintEvent(QPaintEvent*) {
    const auto& colors = Theme::palette();

    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);

    QFont titleFont = font();
    titleFont.setBold(true);
    const QFontMetrics fm(titleFont);
    const int titleH = title_.isEmpty() ? 0 : fm.height();
    const int titleW = title_.isEmpty() ? 0 : fm.horizontalAdvance(title_);

    const int borderTop = titleH / 2;
    QRect border = rect().adjusted(1, borderTop + 1, -1, -1);
    p.setPen(QPen(colors.border, 1.0));
    p.setBrush(Qt::NoBrush);
    p.drawRoundedRect(border, kRadius, kRadius);

    if (!title_.isEmpty()) {
        const int padding = 6;
        const QRect titleRect(kTitleLeftPad - padding, 0,
                              titleW + 2 * padding, titleH);
        p.setBrush(palette().color(QPalette::Window));
        p.setPen(Qt::NoPen);
        p.drawRect(titleRect);

        p.setFont(titleFont);
        p.setPen(colors.windowText);
        p.drawText(QRect(kTitleLeftPad, 0, titleW, titleH),
                   Qt::AlignLeft | Qt::AlignVCenter, title_);
    }
}

}  // namespace sli::toolkit
