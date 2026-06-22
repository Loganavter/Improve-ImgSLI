#include "sli/toolkit/composite/dialog_shell.h"

#include <QHBoxLayout>
#include <QScrollArea>
#include <QStackedWidget>
#include <QVBoxLayout>

#include "sli/toolkit/composite/unified_flyout/minimalist_scrollbar.h"

namespace sli::toolkit {

// ---------------------------------------------------------------------------
// ScrollableDialogPage
// ---------------------------------------------------------------------------

ScrollableDialogPage::ScrollableDialogPage(int contentLeft, int contentTop,
                                           int contentRight, int contentBottom,
                                           int contentSpacing,
                                           QWidget* parent)
    : QWidget(parent) {
  auto* layout = new QVBoxLayout(this);
  layout->setContentsMargins(0, 0, 0, 0);
  layout->setSpacing(0);

  scrollArea_ = new QScrollArea(this);
  scrollArea_->setWidgetResizable(true);
  scrollArea_->setFrameShape(QFrame::NoFrame);
  scrollArea_->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
  scrollArea_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
  scrollArea_->setVerticalScrollBar(new unified_flyout::MinimalistScrollBar());
  scrollArea_->setHorizontalScrollBar(
      new unified_flyout::MinimalistScrollBar());

  contentWidget_ = new QWidget();
  contentLayout_ = new QVBoxLayout(contentWidget_);
  contentLayout_->setContentsMargins(contentLeft, contentTop, contentRight,
                                     contentBottom);
  contentLayout_->setSpacing(contentSpacing);
  contentLayout_->setAlignment(Qt::AlignTop | Qt::AlignLeft);

  scrollArea_->setWidget(contentWidget_);
  layout->addWidget(scrollArea_);
}

// ---------------------------------------------------------------------------
// SidebarDialogShell
// ---------------------------------------------------------------------------

SidebarDialogShell::SidebarDialogShell(int sidebarWidth, int contentLeft,
                                       int contentTop, int contentRight,
                                       int contentBottom, int contentSpacing,
                                       QWidget* parent)
    : QWidget(parent) {
  mainLayout_ = new QHBoxLayout(this);
  mainLayout_->setContentsMargins(0, 0, 0, 0);
  mainLayout_->setSpacing(0);

  // IconListWidget is forward-declared; not yet ported from Python.
  sidebar_ = nullptr;  // will be assigned by derived class or factory

  contentArea_ = new QWidget();
  contentLayout_ = new QVBoxLayout(contentArea_);
  contentLayout_->setContentsMargins(contentLeft, contentTop, contentRight,
                                     contentBottom);
  contentLayout_->setSpacing(contentSpacing);

  pagesStack_ = new QStackedWidget();
  contentLayout_->addWidget(pagesStack_);
}

}  // namespace sli::toolkit