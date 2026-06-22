#pragma once

#include <QIcon>
#include <QList>
#include <QMap>
#include <QObject>
#include <QPointer>
#include <QSize>
#include <QString>
#include <QTimer>
#include <QWidget>

#include <functional>
#include <optional>

class QHBoxLayout;
class QVBoxLayout;

namespace sli::toolkit {

// Forward declarations
class Button;

/// Mirrors Python ``IconAction`` dataclass.
struct IconActionItem {
    QString actionId;
    QIcon icon;
    QString tooltip;
    bool visible = true;
    bool enabled = true;
};

// ---------------------------------------------------------------------------
// IconActionFlyout — mirrors Python ``IconActionFlyout(BaseFlyout)``
// ---------------------------------------------------------------------------
class IconActionFlyout : public QWidget {
    Q_OBJECT

 public:
  explicit IconActionFlyout(QWidget* parent = nullptr,
                            const QList<IconActionItem>& actions = {},
                            int buttonSize = 28,
                            int iconSize = 18);
  ~IconActionFlyout() override = default;

  void setActions(const QList<IconActionItem>& actions);
  Button* actionButton(const QString& actionId) const;

  void setActionState(const QString& actionId,
                      std::optional<QIcon> icon = std::nullopt,
                      std::optional<QString> tooltip = std::nullopt,
                      std::optional<bool> visible = std::nullopt,
                      std::optional<bool> enabled = std::nullopt);

  void showAbove(QWidget* anchor);

  void showAligned(QWidget* anchorWidget,
                   const QString& anchorPoint = QStringLiteral("top-center"),
                   const QString& flyoutPoint = QStringLiteral("bottom-center"),
                   int offset = 5);

  void scheduleAutoHide(int ms);
  void cancelAutoHide();
  void updateState();

 signals:
  void actionTriggered(const QString& actionId);
  void elementHovered(const QString& elementName);
  void elementHoverEnded();

 protected:
  bool eventFilter(QObject* obj, QEvent* event) override;

 public slots:
  void hide();

 private:
  void triggerAction(const QString& actionId);

  QString hoveredElement_;
  QPointer<QWidget> anchorButton_;
  int buttonSize_ = 28;
  int iconSize_ = 18;
  QMap<QString, IconActionItem> actions_;
  QMap<QString, QPointer<Button>> buttons_;
  QHBoxLayout* hLayout_ = nullptr;

  // In-window surface (replaces Python BaseFlyout's container/content_layout)
  QWidget* container_ = nullptr;
  QVBoxLayout* contentLayout_ = nullptr;
  QTimer* autoHideTimer_ = nullptr;
};

}  // namespace sli::toolkit