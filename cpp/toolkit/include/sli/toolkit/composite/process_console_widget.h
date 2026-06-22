#pragma once

#include <QProcess>
#include <QString>
#include <QTextEdit>
#include <QWidget>

#include <vector>

#include "sli/toolkit/atomic/custom_line_edit.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/composite/unified_flyout/minimalist_scrollbar.h"

class QHBoxLayout;

namespace sli::toolkit {

// -----------------------------------------------------------------------
// ProcessConsoleWidget — interactive terminal-style console with QProcess
// integration.  Mirrors Python ProcessConsoleWidget 1:1.
// -----------------------------------------------------------------------
class ProcessConsoleWidget : public QWidget {
    Q_OBJECT

public:
    explicit ProcessConsoleWidget(QWidget* parent = nullptr,
                                  int maxEntries = 2000);

    void setMaxEntries(int maxEntries);
    void clearOutput();
    bool isRunning() const;

    void startProcess(const QString& program,
                      const QStringList& args = {},
                      const QString& workdir = {},
                      const QProcessEnvironment& env = {});

    void startShell(const QString& workdir = {});

    void sendInput(const QString& text, bool addNewline = true,
                   bool echo = true);
    void submitCurrentInput();
    void stopProcess(bool force = false);

signals:
    void outputReceived(const QString& text);
    void errorReceived(const QString& text);
    void commandSubmitted(const QString& command);
    void processStarted();
    void processFinished(int exitCode, int exitStatus);
    void processStateChanged(int state);

private slots:
    void onStdoutReady();
    void onStderrReady();
    void onStarted();
    void onFinished(int exitCode, QProcess::ExitStatus exitStatus);
    void onStateChanged(QProcess::ProcessState state);

private:
    void appendEntry(const QString& level, const QString& text);
    void rebuild();
    void applyStyles();

    int maxEntries_;
    std::vector<std::pair<QString, QString>> entries_;
    QTextEdit* output_ = nullptr;
    QWidget* inputRow_ = nullptr;
    CustomLineEdit* inputEdit_ = nullptr;
    Button* sendButton_ = nullptr;
    unified_flyout::MinimalistScrollBar* scrollbar_ = nullptr;
    QProcess* process_ = nullptr;
};

}  // namespace sli::toolkit
