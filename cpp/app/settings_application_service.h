// Phase 4: thin C++ port of src/plugins/settings/application_service.py.
//
// Computes the field-level diff between the previous and current
// SettingsDialogData (Rust does the actual diff), then for each changed
// field:
//   1. dispatches a Store action if one is wired up for it, and
//   2. persists the value to QSettings under the legacy key.
//
// Coverage is intentionally narrower than the Python service: only fields
// with a Rust Action variant get a dispatch. Everything else is still
// persisted to QSettings so a restart-from-disk reproduces the change.
// Remaining typed actions land alongside their feature ports.

#pragma once

#include <QObject>
#include <QSettings>
#include <QString>

namespace imgsli::app {

class Store;

class SettingsApplicationService final : public QObject {
  Q_OBJECT

 public:
  SettingsApplicationService(Store* store, QSettings* settings,
                             QObject* parent = nullptr);

  /// Apply the diff between `prev_json` and `next_json` (both
  /// `SettingsDialogData`). Returns the number of fields that changed.
  int apply(const QString& prev_json, const QString& next_json);

 signals:
  /// Emitted once after the diff is fully applied. Receivers (e.g. the
  /// main window) can use this to trigger a viewport refresh.
  void applied(int changes);

 private:
  void dispatchForField(const QString& field, const QString& value_json);
  void persist(const QString& field, const QString& value_json);

  Store* store_;
  QSettings* settings_;
};

}  // namespace imgsli::app
