#pragma once

#include <QIcon>
#include <QList>
#include <QMap>
#include <QObject>
#include <QPointer>
#include <QString>
#include <QTimer>
#include <QWidget>

#include <functional>
#include <optional>

class QHBoxLayout;
class QLabel;
class QProgressBar;
class QVBoxLayout;

namespace sli::toolkit {

/// Mirrors Python's ``success`` boolean — defines the toast visual style.
enum class ToastType {
    Info,
    Success,
    Warning,
    Error,
};

/// Mirrors Python ``ToastAction`` dataclass.
struct ToastConfig {
    QString text;
    std::function<void()> callback = nullptr;
    bool dismiss = true;
    QIcon icon;
    QString variant = QStringLiteral("surface");
};

// ---------------------------------------------------------------------------
// ToastWidget — mirrors Python ``ToastNotification``
// ---------------------------------------------------------------------------
class ToastWidget : public QWidget {
    Q_OBJECT

 public:
  explicit ToastWidget(QWidget* parent);
  ~ToastWidget() override = default;

  void showMessage(const QString& content, int maxWidth,
                   int duration = 3000,
                   const QList<ToastConfig>& actions = {},
                   std::optional<int> progress = std::nullopt);

  void updateMessage(const QString& content, int maxWidth, bool success,
                     int duration = 4000,
                     const QList<ToastConfig>& actions = {},
                     std::optional<int> progress = std::nullopt);

  void hideAndClose();

 protected:
  void paintEvent(QPaintEvent* event) override;
  void mousePressEvent(QMouseEvent* event) override;

 private:
  void setActions(const QList<ToastConfig>& actions);
  void applyContentLayoutState();
  void setContent(const QString& content, int maxWidth);
  void setMessageText(const QString& message, int maxWidth);
  void fitToContent(int maxWidth);
  void setProgress(std::optional<int> progress);
  void applyDuration(int duration);
  void applySurfaceState();
  void repolishSurfaceWidgets();
  void onThemeChanged();
  void handleActionClicked(std::function<void()> callback, bool dismiss);

  QVBoxLayout* rootLayout_ = nullptr;
  QWidget* contentWidget_ = nullptr;
  QVBoxLayout* mainLayout_ = nullptr;
  QLabel* messageLabel_ = nullptr;
  QWidget* actionRow_ = nullptr;
  QHBoxLayout* actionRowLayout_ = nullptr;
  QWidget* progressContainer_ = nullptr;
  QVBoxLayout* progressLayout_ = nullptr;
  QProgressBar* progressBar_ = nullptr;
  QTimer* hideTimer_ = nullptr;

  QWidget* customContent_ = nullptr;
  QList<QWidget*> actionWidgets_;

  static constexpr int kMarginsWithAction[4] = {12, 10, 12, 10};
  static constexpr int kMarginsNoAction[4]  = {12, 10, 12, 6};
};

// ---------------------------------------------------------------------------
// ToastManager — mirrors Python ``ToastManager``
// ---------------------------------------------------------------------------
class ToastManager : public QObject {
    Q_OBJECT

 public:
  explicit ToastManager(QWidget* parentWindow, QWidget* imageLabel = nullptr);
  ~ToastManager() override = default;

  int showToast(const QString& content,
                int duration = 3000,
                const QList<ToastConfig>& actions = {},
                std::optional<int> progress = std::nullopt,
                bool success = false);

  void updateToast(int toastId,
                   const QString& content = {},
                   bool success = false,
                   int duration = 3000,
                   const QList<ToastConfig>& actions = {},
                   std::optional<int> progress = std::nullopt);

  void closeToast(int toastId);

 protected:
  bool eventFilter(QObject* watched, QEvent* event) override;

 private:
  int toastMaxWidth() const;
  void positionToasts();

  QPointer<QWidget> parentWindow_;
  QPointer<QWidget> imageLabel_;
  int nextId_ = 1;
  QMap<int, QPointer<ToastWidget>> toasts_;
  int spacing_ = 10;
};

}  // namespace sli::toolkit