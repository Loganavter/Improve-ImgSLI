#pragma once

#include <QString>
#include <QStringList>
#include <QWidget>

namespace sli::toolkit {

// Dashed-border drop target that accepts file URLs and emits the local
// paths. Mirrors Python atomic/drop_zone_label.py for the file-drop case.
class DropZoneLabel final : public QWidget {
  Q_OBJECT

 public:
  explicit DropZoneLabel(const QString& promptText = {},
                         QWidget* parent = nullptr);

  void setPromptText(const QString& text);

 signals:
  void filesDropped(const QStringList& paths);

 protected:
  void paintEvent(QPaintEvent* event) override;
  void dragEnterEvent(QDragEnterEvent* event) override;
  void dragLeaveEvent(QDragLeaveEvent* event) override;
  void dropEvent(QDropEvent* event) override;

 private:
  QString prompt_;
  bool dragHovered_ = false;
};

}  // namespace sli::toolkit
