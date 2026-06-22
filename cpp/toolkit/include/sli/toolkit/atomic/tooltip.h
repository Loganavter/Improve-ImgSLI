#pragma once

#include <QEvent>
#include <QLabel>
#include <QObject>
#include <QPoint>
#include <QPointer>
#include <QString>
#include <QTimer>
#include <QVBoxLayout>
#include <QWidget>

#include "sli/toolkit/helpers/shadow_painter.h"
#include "sli/toolkit/theme.h"

#include <functional>

class QApplication;

namespace sli::toolkit {

// ---------------------------------------------------------------------------
// _TooltipBubble  →  TooltipBubble
// ---------------------------------------------------------------------------
// Translucent overlay widget that renders a QLabel inside a rounded shadow.
class TooltipBubble final : public QWidget {
  Q_OBJECT

 public:
  static constexpr int kShadowRadius = 8;
  static constexpr int kContentRadius = 5;

  explicit TooltipBubble(QWidget* parent);
  ~TooltipBubble() override = default;

  void setText(const QString& text);
  QLabel* label() const { return label_; }

 protected:
  void paintEvent(QPaintEvent* event) override;

 private:
  QLabel* label_ = nullptr;
};

// ---------------------------------------------------------------------------
// _TooltipInterceptor  →  TooltipInterceptor
// ---------------------------------------------------------------------------
class TooltipInterceptor final : public QObject {
  Q_OBJECT

 public:
  using QObject::QObject;

 protected:
  bool eventFilter(QObject* watched, QEvent* event) override;
};

// ---------------------------------------------------------------------------
// _ApplicationTooltipInterceptor  →  ApplicationTooltipInterceptor
// ---------------------------------------------------------------------------
class ApplicationTooltipInterceptor final : public QObject {
  Q_OBJECT

 public:
  using QObject::QObject;

 protected:
  bool eventFilter(QObject* watched, QEvent* event) override;
};

// ---------------------------------------------------------------------------
// PathTooltip  (singleton)
// ---------------------------------------------------------------------------
class PathTooltip final : public QObject {
  Q_OBJECT

 public:
  static constexpr int kDefaultShowDelayMs = 500;

  static PathTooltip& instance();

  // --- public API ---
  void showTooltip(QPoint pos, const QString& text,
                   std::optional<int> delayMs = std::nullopt);
  void hideTooltip();

  void setEnabled(bool enabled);
  bool isEnabled() const { return enabled_; }

  void setShowDelayMs(int delayMs);
  int showDelayMs() const { return showDelayMs_; }

 protected:
  bool eventFilter(QObject* watched, QEvent* event) override;

 private:
  // Singleton
  PathTooltip();
  ~PathTooltip() override = default;
  PathTooltip(const PathTooltip&) = delete;
  PathTooltip& operator=(const PathTooltip&) = delete;

  // Internal helpers
  static bool isAlive(QWidget* widget);
  QWidget* resolveHost(const QPoint& globalPos);
  TooltipBubble* ensureLabel(QWidget* host);
  void applyStyle();
  void showNow(const QPoint& pos, const QString& text);
  void showPendingTooltip();
  void clearLabelRef();

  // State
  QPointer<TooltipBubble> label_;
  QPointer<QWidget> host_;
  bool enabled_ = true;
  int showDelayMs_ = kDefaultShowDelayMs;

  // Pending (deferred) tooltip
  QPoint pendingPos_;
  QString pendingText_;
  int pendingDelayMs_ = 0;

  // Timer for deferred show
  QTimer showTimer_;
};

// ---------------------------------------------------------------------------
// Free helper functions
// ---------------------------------------------------------------------------

/// Returns true if `watched` is a QWidget that should receive a custom
/// tooltip (not disabled via `_disable_custom_tooltip` property, has a
/// non-empty toolTip() string).
bool shouldHandleTooltipWidget(QObject* watched);

/// Install a per-widget tooltip interceptor on `widget`.
/// Corresponds to Python `install_custom_tooltip(widget)`.
void installCustomTooltip(QWidget* widget);

/// Install an application-wide tooltip interceptor on `app`.
/// Corresponds to Python `install_application_tooltips(app)`.
void installApplicationTooltips(QApplication* app);

/// Enable or disable the global PathTooltip.
/// Corresponds to Python `set_application_tooltips_enabled(enabled)`.
void setApplicationTooltipsEnabled(bool enabled);

/// Returns whether the global PathTooltip is currently enabled.
/// Corresponds to Python `application_tooltips_enabled()`.
bool applicationTooltipsEnabled();

}  // namespace sli::toolkit
