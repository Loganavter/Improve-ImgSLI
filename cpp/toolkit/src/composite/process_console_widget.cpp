#include "sli/toolkit/composite/process_console_widget.h"

#include <QFontDatabase>
#include <QHBoxLayout>
#include <QScrollBar>
#include <QStyle>
#include <QVBoxLayout>

#include <cstdlib>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

// -----------------------------------------------------------------------
// Helper: extract enum integer value — mirrors Python _qt_enum_value()
// -----------------------------------------------------------------------
namespace {
int qtEnumValue(int value) { return value; }
}  // namespace

// =======================================================================
// Constructor
// =======================================================================
ProcessConsoleWidget::ProcessConsoleWidget(QWidget* parent, int maxEntries)
    : QWidget(parent),
      maxEntries_(std::max(1, maxEntries)) {

    process_ = new QProcess(this);

    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(8);

    // --- Output area ---
    output_ = new QTextEdit(this);
    output_->setObjectName(QStringLiteral("ProcessConsoleOutput"));
    output_->setFrameShape(QFrame::NoFrame);
    output_->setReadOnly(true);
    output_->setTextInteractionFlags(
        Qt::TextSelectableByMouse | Qt::TextSelectableByKeyboard);
    output_->viewport()->setCursor(Qt::IBeamCursor);

    QFont fixedFont = QFontDatabase::systemFont(QFontDatabase::FixedFont);
    output_->setFont(fixedFont);

    scrollbar_ = new unified_flyout::MinimalistScrollBar(output_);
    output_->setVerticalScrollBar(scrollbar_);
    output_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);

    // --- Input row ---
    inputRow_ = new QWidget(this);
    auto* inputLayout = new QHBoxLayout(inputRow_);
    inputLayout->setContentsMargins(0, 0, 0, 0);
    inputLayout->setSpacing(8);

    inputEdit_ = new CustomLineEdit(inputRow_);
    inputEdit_->setObjectName(QStringLiteral("ProcessConsoleInput"));
    inputEdit_->setPlaceholderText(QStringLiteral("Enter command"));
    inputEdit_->setFont(fixedFont);

    sendButton_ = new Button(Button::Config{
        .text = QStringLiteral("Send"),
        .variant = Button::Variant::Surface,
    }, inputRow_);

    QObject::connect(sendButton_, &QAbstractButton::clicked,
                     this, &ProcessConsoleWidget::submitCurrentInput);
    QObject::connect(inputEdit_, &QLineEdit::returnPressed,
                     this, &ProcessConsoleWidget::submitCurrentInput);

    inputLayout->addWidget(inputEdit_, 1);
    inputLayout->addWidget(sendButton_);

    layout->addWidget(output_, 1);
    layout->addWidget(inputRow_);

    // --- Process signals ---
    QObject::connect(process_, &QProcess::readyReadStandardOutput,
                     this, &ProcessConsoleWidget::onStdoutReady);
    QObject::connect(process_, &QProcess::readyReadStandardError,
                     this, &ProcessConsoleWidget::onStderrReady);
    QObject::connect(process_, &QProcess::started,
                     this, &ProcessConsoleWidget::onStarted);
    QObject::connect(process_, &QProcess::finished,
                     this, &ProcessConsoleWidget::onFinished);
    QObject::connect(process_, &QProcess::stateChanged,
                     this, &ProcessConsoleWidget::onStateChanged);

    // --- Theme ---
    Theme::onThemeChanged(this, [this]() { applyStyles(); });
    applyStyles();
}

// =======================================================================
// Public API
// =======================================================================
void ProcessConsoleWidget::setMaxEntries(int maxEntries) {
    maxEntries_ = std::max(1, maxEntries);
    if (static_cast<int>(entries_.size()) > maxEntries_) {
        entries_.erase(entries_.begin(),
                       entries_.begin() + (entries_.size() - maxEntries_));
    }
    rebuild();
}

void ProcessConsoleWidget::clearOutput() {
    entries_.clear();
    output_->clear();
}

bool ProcessConsoleWidget::isRunning() const {
    return process_->state() != QProcess::NotRunning;
}

void ProcessConsoleWidget::startProcess(const QString& program,
                                         const QStringList& args,
                                         const QString& workdir,
                                         const QProcessEnvironment& env) {
    if (isRunning())
        stopProcess(true);

    clearOutput();
    process_->setProgram(program);
    process_->setArguments(args);
    if (!workdir.isEmpty())
        process_->setWorkingDirectory(workdir);
    if (!env.isEmpty())
        process_->setProcessEnvironment(env);
    process_->start();
}

void ProcessConsoleWidget::startShell(const QString& workdir) {
#ifdef Q_OS_WIN
    startProcess(QStringLiteral("cmd.exe"), {}, workdir);
#else
    QString shell = QString::fromLocal8Bit(std::getenv("SHELL"));
    if (shell.isEmpty())
        shell = QStringLiteral("/bin/bash");
    QStringList args;
    QString baseName = shell.section(QLatin1Char('/'), -1);
    if (baseName == QStringLiteral("bash") ||
        baseName == QStringLiteral("zsh") ||
        baseName == QStringLiteral("sh")) {
        args << QStringLiteral("-i");
    }
    startProcess(shell, args, workdir);
#endif
}

void ProcessConsoleWidget::sendInput(const QString& text, bool addNewline,
                                      bool echo) {
    if (!isRunning()) {
        if (echo && !text.isEmpty())
            appendEntry(QStringLiteral("command"),
                        QStringLiteral("> %1").arg(text));
        appendEntry(QStringLiteral("status"),
                    QStringLiteral("No process running. Call startProcess() or startShell() first."));
        return;
    }

    QString payload = text;
    if (echo && !payload.isEmpty())
        appendEntry(QStringLiteral("command"),
                    QStringLiteral("> %1").arg(payload));
    if (addNewline)
        payload += QChar::LineFeed;
    process_->write(payload.toUtf8());
    emit commandSubmitted(text);
}

void ProcessConsoleWidget::submitCurrentInput() {
    QString text = inputEdit_->text().trimmed();
    if (text.isEmpty())
        return;
    sendInput(text);
    inputEdit_->clear();
}

void ProcessConsoleWidget::stopProcess(bool force) {
    if (!isRunning())
        return;
    if (force)
        process_->kill();
    else
        process_->terminate();
}

// =======================================================================
// Private slots
// =======================================================================
void ProcessConsoleWidget::onStdoutReady() {
    QByteArray data = process_->readAllStandardOutput();
    if (data.isEmpty())
        return;
    QString text = QString::fromUtf8(data);
    for (const QString& line : text.split(QLatin1Char('\n'))) {
        if (!line.isEmpty())
            appendEntry(QStringLiteral("info"), line);
    }
    emit outputReceived(text);
}

void ProcessConsoleWidget::onStderrReady() {
    QByteArray data = process_->readAllStandardError();
    if (data.isEmpty())
        return;
    QString text = QString::fromUtf8(data);
    for (const QString& line : text.split(QLatin1Char('\n'))) {
        if (!line.isEmpty())
            appendEntry(QStringLiteral("error"), line);
    }
    emit errorReceived(text);
}

void ProcessConsoleWidget::onStarted() {
    appendEntry(QStringLiteral("status"), QStringLiteral("Process started"));
    emit processStarted();
}

void ProcessConsoleWidget::onFinished(int exitCode,
                                       QProcess::ExitStatus exitStatus) {
    appendEntry(QStringLiteral("status"),
                QStringLiteral("Process finished with exit code %1").arg(exitCode));
    emit processFinished(exitCode, static_cast<int>(exitStatus));
}

void ProcessConsoleWidget::onStateChanged(QProcess::ProcessState state) {
    emit processStateChanged(static_cast<int>(state));
}

// =======================================================================
// Private helpers
// =======================================================================
void ProcessConsoleWidget::appendEntry(const QString& level,
                                        const QString& text) {
    static const QSet<QString> valid = {
        QStringLiteral("info"),
        QStringLiteral("error"),
        QStringLiteral("status"),
        QStringLiteral("command"),
    };
    QString safeLevel = valid.contains(level) ? level : QStringLiteral("info");
    QString message = text;

    entries_.emplace_back(safeLevel, message);
    if (static_cast<int>(entries_.size()) > maxEntries_)
        entries_.erase(entries_.begin());

    output_->append(
        QStringLiteral("<span class=\"%1\">%2</span>")
            .arg(safeLevel, message.toHtmlEscaped()));
    output_->ensureCursorVisible();
}

void ProcessConsoleWidget::rebuild() {
    output_->blockSignals(true);
    output_->clear();
    for (const auto& [level, message] : entries_) {
        output_->append(
            QStringLiteral("<span class=\"%1\">%2</span>")
                .arg(level, message.toHtmlEscaped()));
    }
    output_->ensureCursorVisible();
    output_->blockSignals(false);
}

void ProcessConsoleWidget::applyStyles() {
    QColor infoColor = Theme::getColor(QStringLiteral("dialog.text"));
    QColor bgColor = Theme::getColor(QStringLiteral("dialog.input.background"));
    QColor borderColor = Theme::getColor(QStringLiteral("input.border.thin"));
    QColor commandColor = Theme::getColor(QStringLiteral("accent"));
    QString errorColor = Theme::isDark()
                             ? QStringLiteral("#D70000")
                             : QStringLiteral("#FF0000");
    QString statusColor = QStringLiteral("#9E9E9E");

    output_->setStyleSheet(
        QStringLiteral(
            "QTextEdit#ProcessConsoleOutput {"
            "  background: %1;"
            "  border: 1px solid %2;"
            "  border-radius: 6px;"
            "  padding: 6px;"
            "  color: %3;"
            "}"
            "QTextEdit#ProcessConsoleOutput QAbstractScrollArea::viewport {"
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
        ".status { color: %3; }"
        ".command { color: %4; font-weight: bold; }")
                             .arg(infoColor.name(), errorColor,
                                  statusColor, commandColor.name());

    output_->document()->setDefaultStyleSheet(stylesheet);
    output_->style()->unpolish(output_);
    output_->style()->polish(output_);
    output_->update();
}

}  // namespace sli::toolkit
