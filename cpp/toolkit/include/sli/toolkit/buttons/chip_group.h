#pragma once

#include <QHash>
#include <QWidget>

class QButtonGroup;
class QHBoxLayout;

namespace sli::toolkit {

class Button;

/// Compact exclusive choice row built from toggle chips.
class ChipGroup final : public QWidget {
  Q_OBJECT

 public:
  explicit ChipGroup(QWidget* parent = nullptr);

  Button* addChip(const QString& id, const QString& text);
  bool removeChip(const QString& id);
  QString currentId() const;
  bool setCurrentId(const QString& id);
  QStringList ids() const;

 signals:
  void currentChanged(const QString& id);

 protected:
  bool eventFilter(QObject* watched, QEvent* event) override;

 private:
  void moveCurrent(int delta);

  QHBoxLayout* layout_ = nullptr;
  QButtonGroup* group_ = nullptr;
  QHash<QString, Button*> chips_;
};

}  // namespace sli::toolkit
