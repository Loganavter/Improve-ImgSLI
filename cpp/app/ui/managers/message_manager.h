#pragma once

#include <QMessageBox>
#include <QObject>
#include <QPointer>
#include <QString>
#include <QVector>

namespace imgsli::app::ui::managers {

// Mirror of Python `src/ui/managers/message_manager.py::MessageManager`. Owns
// a pool of non-modal QMessageBox windows so the UI can fire toast-style
// notifications without blocking the event loop. The host widget owns the
// manager; the manager owns the message boxes via `WA_DeleteOnClose`.
class MessageManager : public QObject {
  Q_OBJECT
 public:
  explicit MessageManager(QWidget* parent);

  void showNonModal(QMessageBox::Icon icon, const QString& title,
                    const QString& text);

 private:
  QPointer<QWidget> parentWidget_;
  QVector<QPointer<QMessageBox>> active_;
};

}  // namespace imgsli::app::ui::managers
