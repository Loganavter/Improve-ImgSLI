#include "sli/toolkit/comboboxes/combo_box.h"

#include <QApplication>
#include <QEvent>
#include <QFocusEvent>
#include <QFontMetrics>
#include <QKeyEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPen>
#include <QRectF>
#include <QTimer>
#include <QWheelEvent>

#include <algorithm>

#include "sli/toolkit/comboboxes/dropdown_overlay.h"
#include "sli/toolkit/comboboxes/search.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit {

// -------------------------------------------------------------------------
// ctor / dtor
// -------------------------------------------------------------------------

ComboBox::ComboBox(QWidget* parent, bool wheelRequiresFocus)
    : Button(
          [&]() -> Button::Config {
              Button::Config cfg;
              cfg.size = QSize(0, kBaseHeight);
              cfg.cornerRadius = kRadius;
              cfg.wheelRequiresFocus = wheelRequiresFocus;
              // deferClick=true: we handle clicks ourselves via regionClicked.
              cfg.deferClick = true;
              return cfg;
          }(),
          parent) {
    setFocusPolicy(Qt::StrongFocus);
    setFixedHeight(kBaseHeight);

    connect(this, &Button::regionClicked, this,
            [this](const QString&) { onFieldClicked(); });
}

ComboBox::~ComboBox() {
    if (QApplication* app = qApp) {
        app->removeEventFilter(this);
    }
    if (QWidget* win = window()) {
        win->removeEventFilter(this);
    }
}

// -------------------------------------------------------------------------
// item management
// -------------------------------------------------------------------------

int ComboBox::count() const {
    return static_cast<int>(items_.size());
}

void ComboBox::addItem(const QString& text, const QVariant& data) {
    items_.emplace_back(text, data);
    if (currentIndex_ == -1) {
        currentIndex_ = 0;
    }
    invalidateVisibleCache();
    update();
}

void ComboBox::addItems(const QStringList& texts) {
    for (const QString& t : texts) {
        addItem(t);
    }
}

void ComboBox::insertItem(int index, const QString& text, const QVariant& data) {
    index = std::max(0, std::min(index, static_cast<int>(items_.size())));
    items_.emplace(items_.begin() + index, text, data);
    if (currentIndex_ == -1) {
        currentIndex_ = 0;
    } else if (index <= currentIndex_) {
        ++currentIndex_;
    }
    invalidateVisibleCache();
    update();
}

void ComboBox::removeItem(int index) {
    if (index < 0 || index >= static_cast<int>(items_.size())) {
        return;
    }
    items_.erase(items_.begin() + index);
    if (items_.empty()) {
        currentIndex_ = -1;
    } else if (currentIndex_ >= static_cast<int>(items_.size())) {
        currentIndex_ = static_cast<int>(items_.size()) - 1;
    } else if (index < currentIndex_) {
        --currentIndex_;
    }
    invalidateVisibleCache();
    scrollOffset_ = std::max(
        0, std::min(scrollOffset_,
                    std::max(0, count() - maxVisibleItems_)));
    update();
}

void ComboBox::clear() {
    hideDropdown();
    items_.clear();
    currentIndex_ = -1;
    scrollOffset_ = 0;
    searchText_.clear();
    invalidateVisibleCache();
    update();
}

// -------------------------------------------------------------------------
// accessors
// -------------------------------------------------------------------------

int ComboBox::currentIndex() const {
    return currentIndex_;
}

QString ComboBox::currentText() const {
    if (currentIndex_ >= 0 && currentIndex_ < static_cast<int>(items_.size())) {
        return items_[currentIndex_].text;
    }
    return {};
}

QVariant ComboBox::currentData() const {
    if (currentIndex_ >= 0 && currentIndex_ < static_cast<int>(items_.size())) {
        return items_[currentIndex_].data;
    }
    return {};
}

QString ComboBox::itemText(int index) const {
    if (index >= 0 && index < static_cast<int>(items_.size())) {
        return items_[index].text;
    }
    return {};
}

QVariant ComboBox::itemData(int index) const {
    if (index >= 0 && index < static_cast<int>(items_.size())) {
        return items_[index].data;
    }
    return {};
}

int ComboBox::findText(const QString& text) const {
    for (int i = 0; i < static_cast<int>(items_.size()); ++i) {
        if (items_[i].text == text) {
            return i;
        }
    }
    return -1;
}

int ComboBox::findData(const QVariant& data) const {
    for (int i = 0; i < static_cast<int>(items_.size()); ++i) {
        if (items_[i].data == data) {
            return i;
        }
    }
    return -1;
}

QList<QPair<QString, QVariant>> ComboBox::items() const {
    QList<QPair<QString, QVariant>> out;
    out.reserve(static_cast<int>(items_.size()));
    for (const auto& item : items_) {
        out.append({item.text, item.data});
    }
    return out;
}

// -------------------------------------------------------------------------
// mutators
// -------------------------------------------------------------------------

void ComboBox::setCurrentIndex(int index) {
    if (index < 0 || index >= static_cast<int>(items_.size())) {
        return;
    }
    if (index == currentIndex_) {
        return;
    }
    currentIndex_ = index;
    ensureCurrentVisible();
    update();
    if (overlay_ && overlay_->isVisible()) {
        overlay_->syncScrollbar();
        overlay_->update();
    }
    if (!signalsBlocked()) {
        emit currentIndexChanged(index);
        emit currentTextChanged(currentText());
    }
}

void ComboBox::setCurrentText(const QString& text) {
    const int idx = findText(text);
    if (idx >= 0) {
        setCurrentIndex(idx);
    }
}

void ComboBox::setCurrentData(const QVariant& data) {
    const int idx = findData(data);
    if (idx >= 0) {
        setCurrentIndex(idx);
    }
}

void ComboBox::setItemText(int index, const QString& text) {
    if (index < 0 || index >= static_cast<int>(items_.size())) {
        return;
    }
    items_[index].text = text;
    items_[index].normalizedText = comboboxes::normalizeForSearch(text);
    invalidateVisibleCache();
    update();
}

void ComboBox::setItemData(int index, const QVariant& data) {
    if (index >= 0 && index < static_cast<int>(items_.size())) {
        items_[index].data = data;
    }
}

// -------------------------------------------------------------------------
// size / layout
// -------------------------------------------------------------------------

void ComboBox::setMaxVisibleItems(int count) {
    maxVisibleItems_ = std::max(1, count);
    if (overlay_ && overlay_->isVisible()) {
        overlay_->showForOwner();
    }
}

int ComboBox::maxVisibleItems() const {
    return maxVisibleItems_;
}

void ComboBox::setMinimumContentsLength(int count) {
    minimumContentsLength_ = std::max(0, count);
    updateGeometry();
}

int ComboBox::contentWidthHint() const {
    QFontMetrics fm(font());
    int textWidth = 0;
    for (const auto& item : items_) {
        textWidth = std::max(textWidth, fm.horizontalAdvance(item.text));
    }
    if (minimumContentsLength_ > 0) {
        textWidth = std::max(textWidth,
                             fm.horizontalAdvance(QString(minimumContentsLength_, QChar('M'))));
    }
    // +24 mirrors Python _content_width_hint: text_width + 24
    return std::max(100, textWidth + 24);
}

QSize ComboBox::sizeHint() const {
    return QSize(contentWidthHint(), kBaseHeight);
}

QSize ComboBox::minimumSizeHint() const {
    return QSize(std::max(80, contentWidthHint()), kBaseHeight);
}

// -------------------------------------------------------------------------
// search
// -------------------------------------------------------------------------

void ComboBox::setSearchEnabled(bool enabled) {
    if (searchEnabled_ == enabled) {
        return;
    }
    searchEnabled_ = enabled;
    if (!enabled) {
        clearSearch();
    }
    invalidateVisibleCache();
    update();
}

bool ComboBox::isSearchEnabled() const {
    return searchEnabled_;
}

QString ComboBox::searchText() const {
    return searchText_;
}

void ComboBox::clearSearch() {
    if (searchText_.isEmpty()) {
        return;
    }
    searchText_.clear();
    invalidateVisibleCache();
    scrollOffset_ = 0;
    if (expanded_ && overlay_) {
        ensureCurrentVisible();
        overlay_->syncScrollbar();
        overlay_->update();
    }
    update();
}

void ComboBox::setSearchTextInternal(const QString& text) {
    if (!searchEnabled_) {
        return;
    }
    if (text == searchText_) {
        return;
    }
    searchText_ = text;
    invalidateVisibleCache();
    const std::vector<int> vis = visibleIndices();
    scrollOffset_ = 0;
    if (!vis.empty()) {
        // setCurrentIndex emits signals; block during search update.
        const QSignalBlocker blocker(this);
        setCurrentIndex(vis[0]);
    }
    if (expanded_ && overlay_) {
        ensureCurrentVisible();
        overlay_->syncScrollbar();
        overlay_->update();
    }
    update();
}

// -------------------------------------------------------------------------
// visible-indices cache
// -------------------------------------------------------------------------

void ComboBox::invalidateVisibleCache() {
    visibleCacheDirty_ = true;
    visibleIndicesCache_.clear();
    visiblePositionsCache_.clear();
}

std::vector<int> ComboBox::visibleIndices() const {
    if (visibleCacheDirty_) {
        std::vector<QString> normalized;
        normalized.reserve(items_.size());
        for (const auto& item : items_) {
            normalized.push_back(item.normalizedText);
        }
        visibleIndicesCache_ = comboboxes::visibleIndices(
            normalized, searchEnabled_, searchText_);
        visiblePositionsCache_.clear();
        for (int pos = 0; pos < static_cast<int>(visibleIndicesCache_.size()); ++pos) {
            visiblePositionsCache_[visibleIndicesCache_[pos]] = pos;
        }
        visibleCacheDirty_ = false;
    }
    return visibleIndicesCache_;
}

int ComboBox::visibleItemCount() const {
    return std::min(static_cast<int>(visibleIndices().size()), maxVisibleItems_);
}

int ComboBox::visiblePositionForIndex(int index) const {
    (void)visibleIndices();  // ensure cache populated
    const auto it = visiblePositionsCache_.find(index);
    return it != visiblePositionsCache_.end() ? it->second : 0;
}

void ComboBox::ensureCurrentVisible() {
    const std::vector<int> vis = visibleIndices();
    const int visCount = static_cast<int>(vis.size());
    if (visCount <= maxVisibleItems_ || currentIndex_ < 0) {
        scrollOffset_ = 0;
        return;
    }
    const auto it = std::find(vis.begin(), vis.end(), currentIndex_);
    if (it == vis.end()) {
        scrollOffset_ = 0;
        return;
    }
    const int visPos = static_cast<int>(std::distance(vis.begin(), it));
    if (visPos < scrollOffset_) {
        scrollOffset_ = visPos;
    } else if (visPos >= scrollOffset_ + maxVisibleItems_) {
        scrollOffset_ = visPos - maxVisibleItems_ + 1;
    }
}

void ComboBox::setScrollOffset(int offset) {
    scrollOffset_ = offset;
}

// -------------------------------------------------------------------------
// visible selection navigation
// -------------------------------------------------------------------------

bool ComboBox::moveVisibleSelection(int step) {
    const std::vector<int> vis = visibleIndices();
    if (vis.empty()) {
        return false;
    }
    const auto it = std::find(vis.begin(), vis.end(), currentIndex_);
    int currentPos = (it != vis.end())
                     ? static_cast<int>(std::distance(vis.begin(), it))
                     : 0;
    int newPos = std::max(0, std::min(static_cast<int>(vis.size()) - 1,
                                     currentPos + step));
    setCurrentIndex(vis[newPos]);
    return true;
}

// -------------------------------------------------------------------------
// dropdown management
// -------------------------------------------------------------------------

bool ComboBox::isExpanded() const {
    return expanded_;
}

void ComboBox::ensureOverlay() {
    QWidget* win = window();
    if (!win) {
        return;
    }
    if (!overlay_ || overlayParent_ != win) {
        overlay_.reset();
        overlayParent_ = win;
        overlay_ = std::make_unique<comboboxes::DropdownOverlay>(this, win);
    }
}

void ComboBox::showDropdown() {
    if (count() == 0) {
        return;
    }
    ensureOverlay();
    if (!overlay_) {
        return;
    }
    expanded_ = true;
    ensureCurrentVisible();
    overlay_->showForOwner();
    update();
    if (QApplication* app = qApp) {
        app->installEventFilter(this);
    }
    if (QWidget* win = window()) {
        win->installEventFilter(this);
    }
}

void ComboBox::hideDropdown() {
    if (overlay_) {
        overlay_->hide();
    }
    expanded_ = false;
    clearSearch();
    update();
    if (QApplication* app = qApp) {
        app->removeEventFilter(this);
    }
    if (QWidget* win = window()) {
        win->removeEventFilter(this);
    }
}

void ComboBox::onFieldClicked() {
    if (expanded_) {
        hideDropdown();
    } else {
        showDropdown();
    }
}

// -------------------------------------------------------------------------
// paintEvent — _ComboFieldBgLayer + _ComboFieldContentLayer
// -------------------------------------------------------------------------
//
// Python's ComboBox replaces Button layers with:
//   [_ComboFieldBgLayer, RippleLayer, _ComboFieldContentLayer]
//
// C++ strategy: paint our bg+border, skip Button::paintEvent (no ripple in
// this phase), paint text+arrow. Ripple can be added in a future phase by
// calling RippleLayer through ButtonController.
//
void ComboBox::paintEvent(QPaintEvent* /*event*/) {
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);

    const QRectF rectf = QRectF(rect()).adjusted(0.5, 0.5, -0.5, -0.5);

    // ---- _ComboFieldBgLayer ----
    QColor bgColor;
    if (isDown() || expanded_) {
        bgColor = Theme::getColor(QStringLiteral("flyout.background"));
    } else if (underMouse()) {
        bgColor = Theme::getColor(QStringLiteral("list_item.background.hover"));
    } else {
        bgColor = Theme::getColor(QStringLiteral("dialog.input.background"));
    }
    painter.setPen(Qt::NoPen);
    painter.setBrush(bgColor);
    painter.drawRoundedRect(rectf, kRadius, kRadius);

    // Border
    painter.setPen(QPen(Theme::getColor(QStringLiteral("input.border.thin")), 1.0));
    painter.setBrush(Qt::NoBrush);
    painter.drawRoundedRect(rectf, kRadius, kRadius);

    // ---- _ComboFieldContentLayer ----
    const QString curText = currentText();
    if (!curText.isEmpty() || (!searchText_.isEmpty() && expanded_)) {
        const bool isDisabled = !isEnabled();
        QColor textColor = Theme::getColor(QStringLiteral("dialog.text"));
        if (isDisabled) {
            textColor.setAlpha(130);
        }

        const int innerH = itemHeight();
        const int innerTop = (height() - innerH) / 2;

        // Python: width - 2 * TEXT_HORIZONTAL_PADDING (fixes clipping: width-24)
        const QRect textRect(
            kTextHorizontalPadding,
            innerTop,
            width() - 2 * kTextHorizontalPadding,
            innerH);

        QString display = curText;
        if (!searchText_.isEmpty() && expanded_) {
            display = searchText_ + QStringLiteral(" -> ") + curText;
        }

        QFontMetrics fm(font());
        painter.setFont(font());
        painter.setPen(QPen(textColor));
        painter.drawText(textRect, Qt::AlignVCenter | Qt::AlignLeft,
                         fm.elidedText(display, Qt::ElideRight, textRect.width()));
    }

    // Arrow — polyline: (cx-4, cy-1), (cx, cy+2), (cx+4, cy-1)
    static constexpr int kArrowRightMargin = 14;
    const double cx = width() - kArrowRightMargin;
    const double cy = height() / 2.0;
    const QPointF poly[3] = {
        QPointF(cx - 4, cy - 1),
        QPointF(cx,     cy + 2),
        QPointF(cx + 4, cy - 1),
    };
    painter.setPen(QPen(Theme::getColor(QStringLiteral("dialog.text")), 1.5));
    painter.setBrush(Qt::NoBrush);
    painter.drawPolyline(poly, 3);
}

// -------------------------------------------------------------------------
// keyboard
// -------------------------------------------------------------------------

void ComboBox::keyPressEvent(QKeyEvent* event) {
    // Backspace — trim search text.
    if (searchEnabled_ && event->key() == Qt::Key_Backspace) {
        if (!searchText_.isEmpty()) {
            setSearchTextInternal(searchText_.chopped(1));
            event->accept();
            return;
        }
    }

    // Plain printable character → search input.
    const QString evText = event->text();
    const bool isPlainText =
        searchEnabled_ &&
        !evText.isEmpty() &&
        evText[0].isPrint() &&
        !(event->modifiers() &
          (Qt::ControlModifier | Qt::AltModifier | Qt::MetaModifier)) &&
        !(event->key() == Qt::Key_Space &&
          searchText_.isEmpty() && !expanded_);

    if (isPlainText) {
        if (!expanded_) {
            showDropdown();
        }
        setSearchTextInternal(searchText_ + evText);
        event->accept();
        return;
    }

    // Return / Enter / Space — toggle dropdown.
    if (event->key() == Qt::Key_Return ||
        event->key() == Qt::Key_Enter  ||
        event->key() == Qt::Key_Space) {
        if (expanded_) {
            hideDropdown();
        } else {
            showDropdown();
        }
        event->accept();
        return;
    }

    // Escape — close.
    if (event->key() == Qt::Key_Escape && expanded_) {
        hideDropdown();
        event->accept();
        return;
    }

    // Down / Up — navigate visible list.
    if (event->key() == Qt::Key_Down && count() > 0) {
        moveVisibleSelection(1);
        event->accept();
        return;
    }
    if (event->key() == Qt::Key_Up && count() > 0) {
        moveVisibleSelection(-1);
        event->accept();
        return;
    }

    Button::keyPressEvent(event);
}

// -------------------------------------------------------------------------
// wheel
// -------------------------------------------------------------------------

void ComboBox::wheelEvent(QWheelEvent* event) {
    if (!isEnabled() || count() <= 1) {
        event->ignore();
        return;
    }
    const int delta = event->angleDelta().y();
    if (delta > 0) {
        setCurrentIndex((currentIndex_ - 1 + count()) % count());
    } else if (delta < 0) {
        setCurrentIndex((currentIndex_ + 1) % count());
    }
    event->accept();
}

// -------------------------------------------------------------------------
// focusOut
// -------------------------------------------------------------------------

void ComboBox::focusOutEvent(QFocusEvent* event) {
    Button::focusOutEvent(event);
    if (!expanded_) {
        return;
    }
    QTimer::singleShot(0, this, [this] { hideDropdownIfFocusLeft(); });
}

bool ComboBox::isDropdownWidget(QWidget* widget) const {
    QWidget* current = widget;
    while (current) {
        if (current == this || current == overlay_.get()) {
            return true;
        }
        current = current->parentWidget();
    }
    return false;
}

void ComboBox::hideDropdownIfFocusLeft() {
    if (!expanded_) {
        return;
    }
    QWidget* next = QApplication::focusWidget();
    QWidget* win = window();
    if (next && isDropdownWidget(next)) {
        return;
    }
    if (win && win->isActiveWindow()) {
        return;
    }
    hideDropdown();
}

// -------------------------------------------------------------------------
// eventFilter
// -------------------------------------------------------------------------

bool ComboBox::eventFilter(QObject* watched, QEvent* event) {
    if (!expanded_ || !overlay_) {
        return Button::eventFilter(watched, event);
    }

    // Reposition on window move/resize.
    if (watched == window() &&
        (event->type() == QEvent::Move || event->type() == QEvent::Resize)) {
        overlay_->showForOwner();
        return false;
    }

    // Close on deactivation / hide / close.
    if (event->type() == QEvent::WindowDeactivate ||
        event->type() == QEvent::ApplicationDeactivate ||
        event->type() == QEvent::Hide ||
        event->type() == QEvent::Close) {
        hideDropdown();
        return false;
    }

    // Close on click outside combo + overlay.
    if (event->type() == QEvent::MouseButtonPress) {
        const auto* me = static_cast<QMouseEvent*>(event);
        const QPoint globalPos = me->globalPosition().toPoint();
        const bool insideField = rect().contains(mapFromGlobal(globalPos));
        const bool insideOverlay = overlay_->geometry().contains(
            overlay_->parentWidget()->mapFromGlobal(globalPos));
        if (!insideField && !insideOverlay) {
            hideDropdown();
        }
    }

    return Button::eventFilter(watched, event);
}

// -------------------------------------------------------------------------
// itemHeight
// -------------------------------------------------------------------------

int ComboBox::itemHeight() const {
    return std::max(28, QFontMetrics(font()).height() + kItemVerticalPadding);
}

}  // namespace sli::toolkit
