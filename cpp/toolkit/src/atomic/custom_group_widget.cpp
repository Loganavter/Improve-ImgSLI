#include "sli/toolkit/atomic/custom_group_widget.h"

#include <QFont>
#include <QFontMetrics>
#include <QLayout>
#include <QPainter>
#include <QVBoxLayout>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

// ======================================================================
// TitleWidgetProxy
// ======================================================================

void TitleWidgetProxy::setText(const QString& text) {
    group_->setTitle(text);
}

QString TitleWidgetProxy::text() const {
    return group_->title();
}

// ======================================================================
// CustomGroupWidget
// ======================================================================

CustomGroupWidget::CustomGroupWidget(const QString& title_text,
                                     QWidget* parent)
    : QWidget(parent),
      title_(title_text),
      content_(new QVBoxLayout(this)) {
    setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Fixed);
    content_->setSpacing(8);
    Theme::onThemeChanged(this, [this]() { update(); });
    updateContentMargins();
}

void CustomGroupWidget::setTitle(const QString& title) {
    if (title_ == title) {
        return;
    }
    title_ = title;
    updateContentMargins();
    updateGeometry();
    update();
}

void CustomGroupWidget::addWidget(QWidget* widget) {
    content_->addWidget(widget);
}

void CustomGroupWidget::addLayout(QLayout* layout) {
    content_->addLayout(layout);
}

void CustomGroupWidget::updateContentMargins() {
    int titleH = 0;
    if (!title_.isEmpty()) {
        QFont f = font();
        f.setBold(true);
        titleH = QFontMetrics(f).height();
    }
    const int topMargin = static_cast<int>(titleH * 0.8) + 12;
    content_->setContentsMargins(12, topMargin, 12, 12);
}

QSize CustomGroupWidget::sizeHint() const {
    const QSize body = content_->sizeHint();

    int titleW = 0;
    if (!title_.isEmpty()) {
        QFont f = font();
        f.setBold(true);
        titleW = QFontMetrics(f).horizontalAdvance(title_);
    }
    const int titleFullWidth = kTitleLeftPad + titleW + 30;
    return {qMax(body.width(), titleFullWidth), body.height()};
}

QSize CustomGroupWidget::minimumSizeHint() const {
    return sizeHint();
}

void CustomGroupWidget::paintEvent(QPaintEvent* event) {
    QWidget::paintEvent(event);

    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);

    // Border colour
    const QColor borderColor = Theme::getColor(QStringLiteral("dialog.border"));
    painter.setPen(QPen(borderColor, kBorderWidth));

    const QRect r = rect();

    // Title metrics
    int titleW = 0;
    int titleH = 0;
    if (!title_.isEmpty()) {
        QFont titleFont = font();
        titleFont.setBold(true);
        const QFontMetrics fm(titleFont);
        titleW = fm.horizontalAdvance(title_);
        titleH = fm.height();
    }
    const int topY = titleH / 2;

    const QRect borderRect(0, topY, r.width() - 1, r.height() - topY - 1);
    painter.drawRoundedRect(borderRect, kRadius, kRadius);

    if (!title_.isEmpty()) {
        // "Erase" background behind the title text
        const int textXStart = kTitleLeftPad;
        const QRect clearRect(textXStart, 0,
                              titleW + kTextPadding * 2, titleH);
        const QColor bgColor =
            Theme::getColor(QStringLiteral("dialog.background"));
        painter.fillRect(clearRect, bgColor);

        // Title text
        QFont titleFont = font();
        titleFont.setBold(true);
        painter.setFont(titleFont);

        const QColor textColor =
            Theme::getColor(QStringLiteral("dialog.text"));
        painter.setPen(textColor);

        const QRect drawRect(textXStart + kTextPadding, 0,
                             titleW, titleH);
        painter.drawText(drawRect,
                         Qt::AlignLeft | Qt::AlignVCenter,
                         title_);
    }
}

// ======================================================================
// CustomGroupBuilder
// ======================================================================

CustomGroupBuilder& CustomGroupBuilder::add(QWidget* widget) {
    pending_.push_back({ItemKind::Widget, static_cast<void*>(widget)});
    return *this;
}

CustomGroupBuilder& CustomGroupBuilder::addLayout(QLayout* layout) {
    pending_.push_back({ItemKind::Layout, static_cast<void*>(layout)});
    return *this;
}

CustomGroupWidget* CustomGroupBuilder::build(const QString& title) {
    auto* group = new CustomGroupWidget(title);
    for (const auto& item : pending_) {
        if (item.kind == ItemKind::Widget) {
            group->addWidget(static_cast<QWidget*>(item.ptr));
        } else {
            group->addLayout(static_cast<QLayout*>(item.ptr));
        }
    }
    pending_.clear();
    return group;
}

std::tuple<CustomGroupWidget*, QVBoxLayout*, TitleWidgetProxy>
CustomGroupBuilder::createStyledGroup(const QString& title_text) {
    auto* group = new CustomGroupWidget(title_text);
    auto* contentLayout = group->contentLayout();
    return std::make_tuple(group, contentLayout, TitleWidgetProxy(group));
}

}  // namespace sli::toolkit