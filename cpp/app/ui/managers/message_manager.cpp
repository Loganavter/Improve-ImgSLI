#include "ui/managers/message_manager.h"

namespace imgsli::app::ui::managers {

MessageManager::MessageManager(QWidget* parent)
    : QObject(parent), parentWidget_(parent) {}

void MessageManager::showNonModal(QMessageBox::Icon icon, const QString& title,
                                  const QString& text) {
  auto* box = new QMessageBox(parentWidget_);
  box->setWindowFlags(box->windowFlags() | Qt::Window);
  box->setAttribute(Qt::WA_DeleteOnClose);
  box->setModal(false);
  box->setIcon(icon);
  box->setWindowTitle(title);
  box->setText(text);

  active_.append(box);
  connect(box, &QMessageBox::finished, this, [this, box]() {
    active_.removeAll(box);
  });

  box->show();
  box->raise();
  box->activateWindow();
}

}  // namespace imgsli::app::ui::managers
