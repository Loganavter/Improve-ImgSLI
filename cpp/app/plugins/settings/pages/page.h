#pragma once

#include <QJsonObject>
#include <QWidget>

namespace imgsli::app::settings_pages {

// Common surface every settings-dialog page implements. Mirrors the
// Python `dialog_pages.py` decomposition: each page owns its widgets and
// knows how to read/write its slice of the dialog JSON.
class SettingsPage : public QWidget {
  Q_OBJECT
 public:
  explicit SettingsPage(QWidget* parent = nullptr) : QWidget(parent) {}
  ~SettingsPage() override = default;

  virtual void load(const QJsonObject& obj) = 0;
  virtual void save(QJsonObject& obj) const = 0;
};

}  // namespace imgsli::app::settings_pages
