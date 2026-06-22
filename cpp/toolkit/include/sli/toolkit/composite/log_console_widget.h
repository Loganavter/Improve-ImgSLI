#pragma once

#include <QString>
#include <QTextEdit>
#include <QVBoxLayout>
#include <QWidget>

#include <optional>
#include <vector>

#include "sli/toolkit/composite/unified_flyout/minimalist_scrollbar.h"

class QScrollBar;

namespace sli::toolkit {

// -----------------------------------------------------------------------
// LogConsoleEntry — immutable log entry.  Mirrors Python LogConsoleEntry
// dataclass 1:1.
// -----------------------------------------------------------------------
struct LogConsoleEntry {
    QString level;
    QString text;
    std::optional<QString> color;
    bool bold = false;
    bool italic = false;
    // metadata omitted — QVariantMap would be the closest, but the C++ side
    // can add it when needed. Python dict[str,Any] is hard to port without
    // a concrete use case.
};

// -----------------------------------------------------------------------
// LogConsoleWidget — read-only log output with level-/color-coded entries.
// Mirrors Python LogConsoleWidget 1:1.
// -----------------------------------------------------------------------
class LogConsoleWidget : public QWidget {
    Q_OBJECT

public:
    explicit LogConsoleWidget(QWidget* parent = nullptr,
                              int maxEntries = 1000);

    void setMaxEntries(int maxEntries);
    void clear();

    [[nodiscard]] std::vector<LogConsoleEntry> entries() const;
    [[nodiscard]] std::vector<LogConsoleEntry> history() const;
    [[nodiscard]] std::vector<QString> plainTextHistory() const;
    [[nodiscard]] QString fullText(const QString& separator = QStringLiteral("\n")) const;

    LogConsoleEntry appendMessage(const QString& text,
                                  const QString& level = QStringLiteral("info"),
                                  std::optional<QColor> color = std::nullopt,
                                  bool bold = false,
                                  bool italic = false);

    LogConsoleEntry appendInfo(const QString& text);
    LogConsoleEntry appendError(const QString& text);
    LogConsoleEntry appendStatus(const QString& text);

    LogConsoleEntry appendEntry(const LogConsoleEntry& entry);

    void setEntries(const std::vector<LogConsoleEntry>& entries);

signals:
    // No signals in Python original — kept for future extensibility.

private:
    void rebuild();
    bool isScrolledToBottom() const;
    void scrollToBottom();
    QString normalizeLevel(const QString& level) const;
    std::optional<QString> normalizeColor(std::optional<QColor> color) const;
    QString entryToHtml(const LogConsoleEntry& entry) const;
    void applyStyles();

    int maxEntries_;
    std::vector<LogConsoleEntry> entries_;
    QTextEdit* output_ = nullptr;
    unified_flyout::MinimalistScrollBar* scrollbar_ = nullptr;
};

}  // namespace sli::toolkit
