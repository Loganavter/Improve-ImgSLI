#pragma once

#include <QColor>
#include <QIcon>
#include <QSize>
#include <QString>
#include <QTabBar>
#include <QVariant>
#include <QWidget>

#include <optional>
#include <utility>
#include <vector>

class QHBoxLayout;

namespace sli::toolkit {

class Button;

/// Policy for showing close buttons on tabs.
enum class CloseButtonPolicy {
  CurrentOnly,
  All,
  AllWhenFitElseCurrent,
};

/// Adaptive tab strip with configurable close-button visibility.
///
/// Mirrors Python sli_ui_toolkit.ui.widgets.composite.adaptive_tab_strip.widget
class AdaptiveTabStrip final : public QWidget {
  Q_OBJECT

 public:
  /// Layout strategy for tabs.
  enum class TabLayout { Fit, Scroll };

  /// A tab close button slot — wraps a Button with vertical offset.
  /// Mirrors Python's _CloseButtonSlot.
  class TabButton final : public QWidget {
   public:
    explicit TabButton(Button* button, int verticalOffset = 1,
                       QWidget* parent = nullptr);
    Button* closeButton() const { return button_; }

   private:
    Button* button_ = nullptr;
  };

  /// Keyword-style config, mirroring Python's keyword-only constructor.
  struct Config {
    QIcon addIcon;
    QIcon closeIcon;
    CloseButtonPolicy closePolicy = CloseButtonPolicy::AllWhenFitElseCurrent;
    bool singleTabClosable = true;
    std::optional<std::vector<std::pair<QString, QVariant>>> addButtonMenu;
    int closeButtonSize = 28;
    int closeIconSize = 16;
    int closeButtonVerticalOffset = 1;
    int marginLeft = 0;
    int marginTop = 4;
    int marginRight = 8;
    int marginBottom = 4;
    int spacing = 2;
  };

  explicit AdaptiveTabStrip(const Config& config, QWidget* parent = nullptr);
  ~AdaptiveTabStrip() override;

  // ---- QTabBar-like compatibility API ----
  int addTab(const QString& text);
  void removeTab(int index);
  int count() const;
  int currentIndex() const;
  void setCurrentIndex(int index);
  void setTabData(int index, const QVariant& data);
  QVariant tabData(int index) const;
  void setTabToolTip(int index, const QString& text);
  QWidget* tabButton(int index, QTabBar::ButtonPosition position) const;
  QRect tabRect(int index) const;

  void refreshCloseButtons();

 signals:
  void currentChanged(int index);
  void tabCloseRequested(int index);
  void addRequested();

 protected:
  void resizeEvent(QResizeEvent* event) override;

 private:
  // ---- internal AdaptiveTabBar (private nested class) ----
  class AdaptiveTabBar;

  friend class AdaptiveTabBar;

  void onCurrentChanged(int index);
  bool shouldShowAllCloseButtons() const;
  bool shouldShowCloseButton(int index, int count, bool showAll) const;
  QWidget* createCloseSlot();
  void emitCloseForSlot(QWidget* slot);

  AdaptiveTabBar* tabBar_ = nullptr;
  Button* addButton_ = nullptr;
  QHBoxLayout* layout_ = nullptr;

  CloseButtonPolicy closePolicy_;
  bool singleTabClosable_;
  bool updatingCloseButtons_ = false;
  QIcon closeIcon_;
  int closeButtonSize_ = 28;
  int closeIconSize_ = 16;
  int closeButtonVerticalOffset_ = 1;
};

}  // namespace sli::toolkit