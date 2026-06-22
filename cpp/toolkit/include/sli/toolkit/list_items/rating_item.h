#pragma once

#include <QEvent>
#include <QHBoxLayout>
#include <QLabel>
#include <QPoint>
#include <QPointF>
#include <QString>
#include <QTimer>

#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/buttons/layers/layer.h"
#include "sli/toolkit/helpers/wheel_scroll_policy.h"

class QMouseEvent;

namespace sli::toolkit {

// -------------------------------------------------------------------------
// Custom layers for RatingListItem
// -------------------------------------------------------------------------

/// Position-aware rounded BG layer: outer corners use outer_r, internal use
/// inner_r. Reads `widget.property("position")` ∈ {"first","middle","last",
/// "only"} and `widget.property("is_current")`, `widget.property("_is_being_dragged")`.
class RatingRowBgLayer final : public buttons::Layer {
public:
    static constexpr int kInnerR = 5;
    static constexpr int kOuterR = 8;

    void draw(const buttons::DrawContext& ctx, const Theme& theme) const override;
};

/// Left accent-bar for current row.
class RatingRowIndicatorLayer final : public buttons::Layer {
public:
    bool applies(const buttons::DrawContext& ctx) const override;
    void draw(const buttons::DrawContext& ctx, const Theme& theme) const override;
};

/// Vertical separator between rating_label and name_label (only for image type).
class RatingRowSeparatorLayer final : public buttons::Layer {
public:
    bool applies(const buttons::DrawContext& ctx) const override;
    void draw(const buttons::DrawContext& ctx, const Theme& theme) const override;
};

// -------------------------------------------------------------------------
// RatingListItem
// -------------------------------------------------------------------------

/// Callback signatures for store interaction (mirroring Python callables).
using GetRatingFn    = std::function<int(int imageNumber, int index)>;
using IncRatingFn    = std::function<void(int imageNumber, int index)>;
using DecRatingFn    = std::function<void(int imageNumber, int index)>;

/// Opaque handle for a rating gesture transaction (mirrors Python's
/// create_rating_gesture). The C++ side stores the returned object and
/// calls commit() or rollback().
class RatingGestureTx {
public:
    virtual ~RatingGestureTx() = default;
    virtual void applyDelta(int delta) = 0;
    virtual void commit() = 0;
    virtual void rollback() = 0;
};
using CreateRatingGestureFn = std::function<std::unique_ptr<RatingGestureTx>(
    int imageNumber, int index, int startingScore)>;

using UpdateDropIndicatorFn = std::function<void(QPoint globalPos)>;
using ClearDropIndicatorFn  = std::function<void()>;

class RatingListItem final : public Button {
    Q_OBJECT

public:
    explicit RatingListItem(
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
        bool isCurrent = false,
        int itemHeight = 36,
        const QFont& itemFont = {},
        const QString& itemType = QStringLiteral("image"),
        const QString& position = QStringLiteral("middle"),
        bool wheelRequiresFocus = false
    );

    ~RatingListItem() override = default;

    // --- Public accessors (mirror Python attributes) ---
    int index() const { return index_; }
    QString fullPath() const { return fullPath_; }
    int imageNumber() const { return imageNumber_; }
    QString itemType() const { return itemType_; }
    QString position() const { return position_; }
    bool isCurrent() const { return isCurrent_; }
    void setCurrent(bool current);

    void setDraggingState(bool isDragging);

    QLabel* ratingLabel() const { return ratingLabel_; }
    QLabel* nameLabel() const { return nameLabel_; }
    Button* minusButton() const { return btnMinus_; }
    Button* plusButton() const { return btnPlus_; }

signals:
    void itemSelected(int index);
    void itemRightClicked(int index);

protected:
    void wheelEvent(QWheelEvent* event) override;
    void enterEvent(QEnterEvent* event) override;
    void leaveEvent(QEvent* event) override;
    void mousePressEvent(QMouseEvent* event) override;
    void mouseMoveEvent(QMouseEvent* event) override;
    void mouseReleaseEvent(QMouseEvent* event) override;
    bool eventFilter(QObject* obj, QEvent* event) override;

private slots:
    void onPlusClicked();
    void onMinusClicked();
    void onButtonPressed();
    void onButtonReleased();
    void showTooltip();
    void updateStyles();

private:
    void cancelButtonInteraction();
    void updateLabelFromStore();
    void notifyFlyoutDropIndicator(QPoint globalPos);
    void notifyFlyoutClearIndicator();

    // Store callbacks
    int index_;
    QString fullPath_;
    int imageNumber_;
    GetRatingFn getRating_;
    IncRatingFn incrementRating_;
    DecRatingFn decrementRating_;
    CreateRatingGestureFn createRatingGesture_;
    UpdateDropIndicatorFn onUpdateDropIndicator_;
    ClearDropIndicatorFn onClearDropIndicator_;

    // Runtime state
    QString itemType_;
    QString position_;
    bool isCurrent_ = false;
    bool isBeingDragged_ = false;
    bool isDragInitiated_ = false;

    // Layout
    QHBoxLayout* rowLayout_ = nullptr;
    QLabel* ratingLabel_ = nullptr;
    QLabel* nameLabel_ = nullptr;
    Button* btnMinus_ = nullptr;
    Button* btnPlus_ = nullptr;

    // Drag / gesture tx
    QPoint dragStartPos_;
    QPointF dragStartPosGlobal_;
    std::unique_ptr<RatingGestureTx> gestureTx_;
    Button* activeButton_ = nullptr;

    // Tooltip
    QTimer tooltipTimer_;
    WheelScrollPolicy wheelPolicy_;
};

}  // namespace sli::toolkit