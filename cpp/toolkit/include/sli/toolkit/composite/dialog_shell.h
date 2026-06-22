#pragma once

#include <QWidget>

class QHBoxLayout;
class QScrollArea;
class QStackedWidget;
class QVBoxLayout;

namespace sli::toolkit {

class IconListWidget;

/// Scrollable page area with MinimalistScrollBars and a content widget.
/// Mirrors Python's ScrollableDialogPage.
class ScrollableDialogPage : public QWidget {
  Q_OBJECT

 public:
  explicit ScrollableDialogPage(
      int contentLeft = 0, int contentTop = 0, int contentRight = 12,
      int contentBottom = 0, int contentSpacing = 15,
      QWidget* parent = nullptr);

  QScrollArea* scrollArea() const { return scrollArea_; }
  QWidget* contentWidget() const { return contentWidget_; }
  QVBoxLayout* contentLayout() const { return contentLayout_; }

 private:
  QScrollArea* scrollArea_ = nullptr;
  QWidget* contentWidget_ = nullptr;
  QVBoxLayout* contentLayout_ = nullptr;
};

/// Sidebar (IconListWidget) + stacked content area shell.
/// Mirrors Python's SidebarDialogShell.
class SidebarDialogShell : public QWidget {
  Q_OBJECT

 public:
  explicit SidebarDialogShell(
      int sidebarWidth = 200, int contentLeft = 20, int contentTop = 20,
      int contentRight = 20, int contentBottom = 20, int contentSpacing = 10,
      QWidget* parent = nullptr);

  IconListWidget* sidebar() const { return sidebar_; }
  QStackedWidget* pagesStack() const { return pagesStack_; }
  QVBoxLayout* contentLayout() const { return contentLayout_; }

 private:
  QHBoxLayout* mainLayout_ = nullptr;
  IconListWidget* sidebar_ = nullptr;
  QWidget* contentArea_ = nullptr;
  QVBoxLayout* contentLayout_ = nullptr;
  QStackedWidget* pagesStack_ = nullptr;
};

}  // namespace sli::toolkit