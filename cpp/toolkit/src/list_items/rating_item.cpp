#include "sli/toolkit/list_items/rating_item.h"

#include <QApplication>
#include <QCursor>
#include <QFontMetrics>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPen>
#include <QTimer>
#include <QVariant>
#include <QWheelEvent>

#include "sli/toolkit/atomic/tooltip.h"

#include "sli/toolkit/buttons/draw_context.h"
#include "sli/toolkit/buttons/layers/ripple_layer.h"
#include "sli/toolkit/helpers/wheel_scroll_policy.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit {
namespace {

// Python's DEFAULT_MINUS_ICON = "remove", DEFAULT_PLUS_ICON = "add"
const QString kMinusIcon = QStringLiteral("remove");
const QString kPlusIcon  = QStringLiteral("add");

}  // namespace

// ---------------------------------------------------------------------------
// RatingRowBgLayer
// ---------------------------------------------------------------------------

void RatingRowBgLayer::draw(const buttons::DrawContext& ctx, const Theme& theme) const {
    auto* widget = ctx.widget;
    const auto states = ctx.effectiveStates();
    const bool isActive = widget->property("is_current").toBool()
        || states.testFlag(buttons::ButtonState::Hovered)
        || states.testFlag(buttons::ButtonState::Pressed);

    const QString key = isActive
        ? QStringLiteral("list_item.background.hover")
        : QStringLiteral("list_item.background.normal");

    QPainter* p = ctx.painter;
    p->setRenderHint(QPainter::Antialiasing);

    const bool beingDragged = widget->property("_is_being_dragged").toBool();
    if (beingDragged)
        p->setOpacity(0.35);

    p->setPen(Qt::NoPen);
    p->setBrush(theme.getColor(key));

    const QRect bgRect = ctx.rect.toRect().adjusted(2, 2, -2, -2);
    const QString pos = widget->property("position").toString();

    if (pos == QStringLiteral("middle")) {
        p->drawRoundedRect(bgRect, kInnerR, kInnerR);
    } else {
        const QRect& r = bgRect;
        const int tl = (pos == QStringLiteral("first") || pos == QStringLiteral("only"))
            ? kOuterR : kInnerR;
        const int tr = tl;
        const int bl = (pos == QStringLiteral("last") || pos == QStringLiteral("only"))
            ? kOuterR : kInnerR;
        const int br = bl;

        QPainterPath path;
        path.moveTo(r.left() + tl, r.top());
        path.lineTo(r.right() - tr, r.top());
        path.arcTo(r.right() - 2 * tr, r.top(), 2 * tr, 2 * tr, 90, -90);
        path.lineTo(r.right(), r.bottom() - br);
        path.arcTo(r.right() - 2 * br, r.bottom() - 2 * br, 2 * br, 2 * br, 0, -90);
        path.lineTo(r.left() + bl, r.bottom());
        path.arcTo(r.left(), r.bottom() - 2 * bl, 2 * bl, 2 * bl, -90, -90);
        path.lineTo(r.left(), r.top() + tl);
        path.arcTo(r.left(), r.top(), 2 * tl, 2 * tl, 180, -90);
        path.closeSubpath();
        p->drawPath(path);
    }

    if (beingDragged)
        p->setOpacity(1.0);
}

// ---------------------------------------------------------------------------
// RatingRowIndicatorLayer
// ---------------------------------------------------------------------------

bool RatingRowIndicatorLayer::applies(const buttons::DrawContext& ctx) const {
    return ctx.widget->property("is_current").toBool();
}

void RatingRowIndicatorLayer::draw(const buttons::DrawContext& ctx, const Theme& theme) const {
    auto* widget = ctx.widget;
    const QRect rect = ctx.rect.toRect();

    QPen pen(theme.getColor(QStringLiteral("accent")));
    pen.setWidth(3);
    pen.setCapStyle(Qt::RoundCap);

    QPainter* p = ctx.painter;
    const bool beingDragged = widget->property("_is_being_dragged").toBool();
    if (beingDragged)
        p->setOpacity(0.35);

    p->setPen(pen);
    const int x = rect.left() + pen.width();
    p->drawLine(x, rect.top() + 7, x, rect.bottom() - 7);

    if (beingDragged)
        p->setOpacity(1.0);
}

// ---------------------------------------------------------------------------
// RatingRowSeparatorLayer
// ---------------------------------------------------------------------------

bool RatingRowSeparatorLayer::applies(const buttons::DrawContext& ctx) const {
    auto* widget = ctx.widget;
    const QString type = widget->property("itemType").toString();
    const bool hasRatingLabel = widget->property("_has_rating_label").toBool();
    return type == QStringLiteral("image") && hasRatingLabel;
}

void RatingRowSeparatorLayer::draw(const buttons::DrawContext& ctx, const Theme& theme) const {
    auto* widget = ctx.widget;
    QPainter* p = ctx.painter;

    const bool beingDragged = widget->property("_is_being_dragged").toBool();
    if (beingDragged)
        p->setOpacity(0.35);

    p->setPen(QPen(theme.getColor(QStringLiteral("separator.color")), 1));

    // The rating_label geometry and layout spacing are communicated via
    // dynamic properties. Fallback to sensible defaults if absent.
    const int ratingRight = widget->property("_rating_label_right").toInt();
    bool spacingOk = false;
    const int spacing = widget->property("_layout_spacing").toInt(&spacingOk);
    const int xPos = spacingOk ? (ratingRight + spacing / 2) : ratingRight;

    p->drawLine(xPos, 6, xPos, widget->height() - 6);

    if (beingDragged)
        p->setOpacity(1.0);
}

// ---------------------------------------------------------------------------
// RatingListItem
// ---------------------------------------------------------------------------

RatingListItem::RatingListItem(
    int index,
    const QString& text,
    int rating,
    const QString& fullPath,
    int imageNumber,
    GetRatingFn getRating,
    IncRatingFn incrementRating,
    DecRatingFn decrementRating,
    CreateRatingGestureFn createRatingGesture,
    UpdateDropIndicatorFn onUpdateDropIndicator,
    ClearDropIndicatorFn onClearDropIndicator,
    QWidget* parent,
    bool isCurrent,
    int itemHeight,
    const QFont& itemFont,
    const QString& itemType,
    const QString& position,
    bool wheelRequiresFocus
)
    : Button(Button::Config{
          .text = {},
          .size = QSize(0, itemHeight),
          .cornerRadius = 8,
          .wheelRequiresFocus = wheelRequiresFocus,
      }, parent)
    , index_(index)
    , fullPath_(fullPath)
    , imageNumber_(imageNumber)
    , getRating_(std::move(getRating))
    , incrementRating_(std::move(incrementRating))
    , decrementRating_(std::move(decrementRating))
    , createRatingGesture_(std::move(createRatingGesture))
    , onUpdateDropIndicator_(std::move(onUpdateDropIndicator))
    , onClearDropIndicator_(std::move(onClearDropIndicator))
    , itemType_(itemType)
    , position_(position)
    , isCurrent_(isCurrent)
    , wheelPolicy_(wheelRequiresFocus)
{
    // Set dynamic properties for layer access (must be set before any paint).
    setProperty("itemType", itemType_);
    setProperty("position", position_);
    setProperty("is_current", isCurrent_);
    setProperty("_is_being_dragged", false);
    setProperty("_has_rating_label", false);

    // Connect to theme changes
    Theme::onThemeChanged(this, [this]() { updateStyles(); });

    // Tooltip timer
    tooltipTimer_.setSingleShot(true);
    tooltipTimer_.setInterval(500);
    connect(&tooltipTimer_, &QTimer::timeout, this, &RatingListItem::showTooltip);

    // Row click → external selection
    connect(this, &Button::clicked, this, [this]() { emit itemSelected(index_); });
    connect(this, &Button::rightClicked, this, [this]() { emit itemRightClicked(index_); });

    // Build row layout
    rowLayout_ = new QHBoxLayout(this);
    rowLayout_->setContentsMargins(2, 2, 2, 2);
    rowLayout_->setSpacing(6);

    if (itemType_ == QStringLiteral("image")) {
        ratingLabel_ = new QLabel(QString::number(rating), this);
        ratingLabel_->setFixedWidth(25);
        ratingLabel_->setAlignment(Qt::AlignCenter);
        ratingLabel_->setObjectName(QStringLiteral("ratingLabel"));
        setProperty("_has_rating_label", true);
    }

    nameLabel_ = new QLabel(text, this);
    nameLabel_->setObjectName(QStringLiteral("nameLabel"));
    nameLabel_->setMinimumWidth(0);
    nameLabel_->setTextInteractionFlags(Qt::NoTextInteraction);
    nameLabel_->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Preferred);

    QFont baseFont = itemFont.exactMatch() ? itemFont : QApplication::font();
    nameLabel_->setFont(baseFont);

    if (itemType_ == QStringLiteral("image")) {
        int basePx = baseFont.pixelSize();
        if (basePx <= 0)
            basePx = QFontMetrics(baseFont).height();
        QFont ratingFont(baseFont);
        ratingFont.setPixelSize(qMax(8, basePx - 3));
        ratingLabel_->setFont(ratingFont);

        btnMinus_ = new Button(Button::Config{
            .icon = QIcon::fromTheme(kMinusIcon),
            .iconSize = 14,
        }, this);
        btnPlus_ = new Button(Button::Config{
            .icon = QIcon::fromTheme(kPlusIcon),
            .iconSize = 14,
        }, this);
        btnMinus_->setObjectName(QStringLiteral("minusButton"));
        btnPlus_->setObjectName(QStringLiteral("plusButton"));

        for (auto* btn : {btnMinus_, btnPlus_}) {
            btn->setFixedSize(22, 22);
            btn->setFocusPolicy(Qt::NoFocus);
            btn->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
        }

        rowLayout_->addWidget(ratingLabel_);
        rowLayout_->addWidget(nameLabel_, 1);
        rowLayout_->addWidget(btnMinus_);
        rowLayout_->addWidget(btnPlus_);

        connect(btnPlus_, &Button::clicked, this, &RatingListItem::onPlusClicked);
        connect(btnMinus_, &Button::clicked, this, &RatingListItem::onMinusClicked);
        connect(btnPlus_, &Button::pressed, this, &RatingListItem::onButtonPressed);
        connect(btnMinus_, &Button::pressed, this, &RatingListItem::onButtonPressed);
        connect(btnPlus_, &Button::released, this, &RatingListItem::onButtonReleased);
        connect(btnMinus_, &Button::released, this, &RatingListItem::onButtonReleased);

        btnPlus_->installEventFilter(this);
        btnMinus_->installEventFilter(this);
    } else {
        rowLayout_->addWidget(nameLabel_, 1);
    }

    updateStyles();
}

void RatingListItem::setCurrent(bool current) {
    isCurrent_ = current;
    setProperty("is_current", current);
    update();
}

void RatingListItem::setDraggingState(bool isDragging) {
    if (isBeingDragged_ != isDragging) {
        isBeingDragged_ = isDragging;
        setProperty("_is_being_dragged", isDragging);
        update();
    }
}

// ---------------------------------------------------------------------------
// Event handling
// ---------------------------------------------------------------------------

void RatingListItem::wheelEvent(QWheelEvent* event) {
    if (!wheelPolicy_.shouldHandleWheelEvent(this, event))
        return;
    if (itemType_ != QStringLiteral("image"))
        return;

    const QPoint pos = event->position().toPoint();
    if (ratingLabel_ && ratingLabel_->geometry().contains(pos)) {
        const int delta = event->angleDelta().y();
        if (delta > 0)
            incrementRating_(imageNumber_, index_);
        else
            decrementRating_(imageNumber_, index_);
        updateLabelFromStore();
        event->accept();
    } else {
        event->ignore();
    }
}

void RatingListItem::enterEvent(QEnterEvent* event) {
    Button::enterEvent(event);
    if (!fullPath_.isEmpty())
        tooltipTimer_.start();
}

void RatingListItem::leaveEvent(QEvent* event) {
    Button::leaveEvent(event);
    tooltipTimer_.stop();
    PathTooltip::instance().hideTooltip();
}

void RatingListItem::mousePressEvent(QMouseEvent* event) {
    tooltipTimer_.stop();
    PathTooltip::instance().hideTooltip();
    if (event->button() == Qt::LeftButton) {
        dragStartPos_ = event->pos();
        dragStartPosGlobal_ = event->globalPosition();
    }
    Button::mousePressEvent(event);
}

void RatingListItem::mouseMoveEvent(QMouseEvent* event) {
    Button::mouseMoveEvent(event);
    if (!(event->buttons() & Qt::LeftButton))
        return;
    if (isDragInitiated_)
        return;

    const QPoint currentGlobal = mapToGlobal(event->pos());
    const QPoint startGlobal  = mapToGlobal(dragStartPos_);
    const int distance = (currentGlobal - startGlobal).manhattanLength();

    if (distance >= QApplication::startDragDistance()) {
        if (itemType_ == QStringLiteral("image") && activeButton_) {
            // Stop the hold-repeat timers on the child buttons (accessed via property).
            auto* delayTimer = activeButton_->property("_initial_delay_timer").value<QObject*>();
            if (auto* t = qobject_cast<QTimer*>(delayTimer))
                t->stop();
            auto* repeatTimer = activeButton_->property("_repeat_timer").value<QObject*>();
            if (auto* t = qobject_cast<QTimer*>(repeatTimer))
                t->stop();
            if (gestureTx_) {
                gestureTx_->rollback();
                gestureTx_.reset();
            }
        }

        tooltipTimer_.stop();
        PathTooltip::instance().hideTooltip();

        isDragInitiated_ = true;
        // NOTE: drag-drop-service integration is a stub — the host app is
        // expected to provide its own mechanism. Python calls
        // get_dragdrop_service().start_drag(self, event).
        notifyFlyoutDropIndicator(event->globalPosition().toPoint());
    }
}

void RatingListItem::mouseReleaseEvent(QMouseEvent* event) {
    if (isDragInitiated_) {
        // Drag swallowed the click — clear pressed state without firing clicked.
        // In Python: self._pressed = False; self._pressed_region = None
        event->accept();
    } else {
        Button::mouseReleaseEvent(event);
    }

    if (itemType_ == QStringLiteral("image") && gestureTx_ && !activeButton_) {
        gestureTx_->commit();
        gestureTx_.reset();
        updateLabelFromStore();
    }

    isDragInitiated_ = false;
    activeButton_ = nullptr;
    notifyFlyoutClearIndicator();
}

bool RatingListItem::eventFilter(QObject* obj, QEvent* event) {
    if (itemType_ != QStringLiteral("image"))
        return Button::eventFilter(obj, event);

    if ((obj == btnPlus_ || obj == btnMinus_) &&
        event->type() == QEvent::MouseMove)
    {
        auto* me = static_cast<QMouseEvent*>(event);
        if (me->buttons() & Qt::LeftButton) {
            if (activeButton_ == obj && !isDragInitiated_) {
                // Stop hold-repeat timers on the child button
                auto* delayTimer = activeButton_->property("_initial_delay_timer").value<QObject*>();
                if (auto* t = qobject_cast<QTimer*>(delayTimer))
                    t->stop();
                auto* repeatTimer = activeButton_->property("_repeat_timer").value<QObject*>();
                if (auto* t = qobject_cast<QTimer*>(repeatTimer))
                    t->stop();
                const qreal distance = (me->globalPosition() - dragStartPosGlobal_).manhattanLength();
                if (distance >= QApplication::startDragDistance()) {
                    cancelButtonInteraction();
                }
            }
            return true;
        }
    }

    return Button::eventFilter(obj, event);
}

// ---------------------------------------------------------------------------
// Private slots / helpers
// ---------------------------------------------------------------------------

void RatingListItem::onPlusClicked() {
    if (isDragInitiated_ || (activeButton_ && activeButton_ != btnPlus_))
        return;
    if (gestureTx_)
        gestureTx_->applyDelta(+1);
    else
        incrementRating_(imageNumber_, index_);
    updateLabelFromStore();
}

void RatingListItem::onMinusClicked() {
    if (isDragInitiated_ || (activeButton_ && activeButton_ != btnMinus_))
        return;
    if (gestureTx_)
        gestureTx_->applyDelta(-1);
    else
        decrementRating_(imageNumber_, index_);
    updateLabelFromStore();
}

void RatingListItem::onButtonPressed() {
    if (itemType_ != QStringLiteral("image"))
        return;
    auto* btn = qobject_cast<Button*>(sender());
    if (!btn)
        return;
    activeButton_ = btn;
    dragStartPosGlobal_ = QPointF(QCursor::pos());
    dragStartPos_ = mapFromGlobal(QCursor::pos());
    const int startingScore = getRating_(imageNumber_, index_);
    gestureTx_ = createRatingGesture_(imageNumber_, index_, startingScore);
}

void RatingListItem::onButtonReleased() {
    auto* btn = qobject_cast<Button*>(sender());
    if (activeButton_ != btn)
        return;
    if (gestureTx_ && !isDragInitiated_) {
        gestureTx_->commit();
        gestureTx_.reset();
        updateLabelFromStore();
    }
    activeButton_ = nullptr;
}

void RatingListItem::cancelButtonInteraction() {
    if (gestureTx_) {
        gestureTx_->rollback();
        gestureTx_.reset();
    }
    activeButton_ = nullptr;
}

void RatingListItem::updateLabelFromStore() {
    if (itemType_ != QStringLiteral("image") || !ratingLabel_)
        return;
    ratingLabel_->setText(QString::number(getRating_(imageNumber_, index_)));
}

void RatingListItem::updateStyles() {
    if (itemType_ == QStringLiteral("image")) {
        if (btnMinus_)
            btnMinus_->setIcon(QIcon::fromTheme(kMinusIcon));
        if (btnPlus_)
            btnPlus_->setIcon(QIcon::fromTheme(kPlusIcon));
    }
    update();
}

void RatingListItem::showTooltip() {
    if (!fullPath_.isEmpty())
        PathTooltip::instance().showTooltip(QCursor::pos(), fullPath_);
}

void RatingListItem::notifyFlyoutDropIndicator(QPoint globalPos) {
    if (onUpdateDropIndicator_)
        onUpdateDropIndicator_(globalPos);
}

void RatingListItem::notifyFlyoutClearIndicator() {
    if (onClearDropIndicator_)
        onClearDropIndicator_();
}

}  // namespace sli::toolkit