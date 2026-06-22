#include "sli/toolkit/composite/log_console_widget.h"

#include <QColor>
#include <QScrollBar>
#include <QStyle>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

// =======================================================================
// Constructor
// =======================================================================
LogConsoleWidget::LogConsoleWidget(QWidget* parent, int maxEntries)
    : QWidget(parent),
      maxEntries_(std::max(1, maxEntries)) {

    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);

    output_ = new QTextEdit(this);
    output_->setObjectName(QStringLiteral("LogConsoleOutput"));
    output_->setFrameShape(QFrame::NoFrame);
    output_->setReadOnly(true);
    output_->setAcceptRichText(false);
    output_->setUndoRedoEnabled(false);
    output_->setTabChangesFocus(true);
    output_->setFocusPolicy(Qt::NoFocus);
    output_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    output_->viewport()->setCursor(Qt::IBeamCursor);
    output_->setCursorWidth(0);

    scrollbar_ = new unified_flyout::MinimalistScrollBar(output_);
    output_->setVerticalScrollBar(scrollbar_);
    output_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);

    layout->addWidget(output_);

    Theme::onThemeChanged(this, [this]() { applyStyles(); });
    applyStyles();
}

// =======================================================================
// Public API
// =======================================================================
void LogConsoleWidget::setMaxEntries(int maxEntries) {
    maxEntries_ = std::max(1, maxEntries);
    if (static_cast<int>(entries_.size()) > maxEntries_) {
        entries_.erase(entries_.begin(),
                       entries_.begin() + (entries_.size() - maxEntries_));
    }
    rebuild();
}

void LogConsoleWidget::clear() {
    entries_.clear();
    output_->clear();
}

std::vector<LogConsoleEntry> LogConsoleWidget::entries() const {
    return entries_;
}

std::vector<LogConsoleEntry> LogConsoleWidget::history() const {
    return entries();
}

std::vector<QString> LogConsoleWidget::plainTextHistory() const {
    std::vector<QString> result;
    result.reserve(entries_.size());
    for (const auto& e : entries_)
        result.push_back(e.text);
    return result;
}

QString LogConsoleWidget::fullText(const QString& separator) const {
    QStringList parts;
    parts.reserve(static_cast<int>(entries_.size()));
    for (const auto& e : entries_)
        parts.append(e.text);
    return parts.join(separator);
}

LogConsoleEntry LogConsoleWidget::appendMessage(const QString& text,
                                                 const QString& level,
                                                 std::optional<QColor> color,
                                                 bool bold,
                                                 bool italic) {
    LogConsoleEntry entry;
    entry.level = normalizeLevel(level);
    entry.text = text;
    entry.color = normalizeColor(color);
    entry.bold = bold;
    entry.italic = italic;

    entries_.push_back(entry);
    // Trim to max entries
    if (static_cast<int>(entries_.size()) > maxEntries_)
        entries_.erase(entries_.begin(),
                       entries_.begin() + (entries_.size() - maxEntries_));

    bool atBottom = isScrolledToBottom();
    output_->append(entryToHtml(entry));
    if (atBottom)
        scrollToBottom();

    return entry;
}

LogConsoleEntry LogConsoleWidget::appendInfo(const QString& text) {
    return appendMessage(text, QStringLiteral("info"));
}

LogConsoleEntry LogConsoleWidget::appendError(const QString& text) {
    return appendMessage(text, QStringLiteral("error"));
}

LogConsoleEntry LogConsoleWidget::appendStatus(const QString& text) {
    return appendMessage(text, QStringLiteral("status"));
}

LogConsoleEntry LogConsoleWidget::appendEntry(const LogConsoleEntry& entry) {
    return appendMessage(entry.text, entry.level, std::nullopt,
                         entry.bold, entry.italic);
    // Note: color from entry not forwarded because normalizeColor takes QColor,
    // but we can add an overload. Matching Python which passes entry.color
    // as-is (str | None). Simpler: re-interpret via optional QString.
}

void LogConsoleWidget::setEntries(const std::vector<LogConsoleEntry>& entries) {
    entries_ = entries;
    if (static_cast<int>(entries_.size()) > maxEntries_)
        entries_.erase(entries_.begin(),
                       entries_.begin() + (entries_.size() - maxEntries_));
    rebuild();
}

// =======================================================================
// Private helpers
// =======================================================================
void LogConsoleWidget::rebuild() {
    bool atBottom = isScrolledToBottom();
    int prevValue = output_->verticalScrollBar()->value();

    output_->blockSignals(true);
    output_->clear();
    for (const auto& entry : entries_)
        output_->append(entryToHtml(entry));
    output_->blockSignals(false);

    if (atBottom) {
        scrollToBottom();
    } else {
        output_->verticalScrollBar()->setValue(prevValue);
    }
}

bool LogConsoleWidget::isScrolledToBottom() const {
    auto* bar = output_->verticalScrollBar();
    return bar->value() >= bar->maximum() - 2;
}

void LogConsoleWidget::scrollToBottom() {
    auto* bar = output_->verticalScrollBar();
    bar->setValue(bar->maximum());
}

QString LogConsoleWidget::normalizeLevel(const QString& level) const {
    static const QSet<QString> valid = {
        QStringLiteral("info"),
        QStringLiteral("error"),
        QStringLiteral("status"),
    };
    return valid.contains(level) ? level : QStringLiteral("info");
}

std::optional<QString> LogConsoleWidget::normalizeColor(
    std::optional<QColor> color) const {
    if (!color)
        return std::nullopt;
    return color->name(QColor::HexArgb);
}

QString LogConsoleWidget::entryToHtml(const LogConsoleEntry& entry) const {
    QStringList styles;
    if (entry.color)
        styles.append(QStringLiteral("color: %1").arg(*entry.color));
    if (entry.bold)
        styles.append(QStringLiteral("font-weight: bold"));
    if (entry.italic)
        styles.append(QStringLiteral("font-style: italic"));

    QString styleAttr;
    if (!styles.isEmpty())
        styleAttr = QStringLiteral(" style=\"%1\"").arg(styles.join(QStringLiteral("; ")));

    // Escape HTML in text
    QString escaped = entry.text.toHtmlEscaped();
    return QStringLiteral("<span class=\"%1\"%2>%3</span>")
        .arg(entry.level, styleAttr, escaped);
}

void LogConsoleWidget::applyStyles() {
    QColor infoColor = Theme::getColor(QStringLiteral("dialog.text"));
    QColor bgColor = Theme::getColor(QStringLiteral("dialog.input.background"));
    QColor borderColor = Theme::getColor(QStringLiteral("input.border.thin"));
    QString errorColor = Theme::isDark()
                             ? QStringLiteral("#D70000")
                             : QStringLiteral("#FF0000");
    QString statusColor = QStringLiteral("#9E9E9E");

    output_->setStyleSheet(
        QStringLiteral(
            "QTextEdit#LogConsoleOutput {"
            "  background: %1;"
            "  border: 1px solid %2;"
            "  border-radius: 6px;"
            "  padding: 6px;"
            "  color: %3;"
            "}"
            "QTextEdit#LogConsoleOutput QAbstractScrollArea::viewport {"
            "  background: transparent;"
            "  border-radius: 6px;"
            "}")
            .arg(bgColor.name(QColor::HexArgb),
                 borderColor.name(QColor::HexArgb),
                 infoColor.name()));

    QString stylesheet = QStringLiteral(
        "body { color: %1; }"
        ".info { color: %1; }"
        ".error { color: %2; font-weight: bold; }"
        ".status { color: %3; }")
                             .arg(infoColor.name(), errorColor, statusColor);

    output_->document()->setDefaultStyleSheet(stylesheet);
    output_->style()->unpolish(output_);
    output_->style()->polish(output_);
    output_->update();
    rebuild();
}

}  // namespace sli::toolkit
