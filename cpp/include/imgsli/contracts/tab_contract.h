// Workspace tab contract — C++ port of src/tabs/contract.py::TabContract.
//
// Each workspace tab is a self-contained mini-app: owns its widget tree,
// resources, translations, and controller state. The host shell hands it
// a slot in the workspace stack and forwards session lifecycle events.
//
// Phase 4 lays the abstraction; concrete tabs (multi-compare, video
// editor, export) port over in Phase 5 alongside their plugins.

#pragma once

#include <QIcon>
#include <QString>
#include <QStringList>
#include <QWidget>

namespace imgsli::contracts {

class TabContract {
 public:
  virtual ~TabContract() = default;

  /// Unique session-type identifier, e.g. "multi_compare".
  virtual QString sessionType() const = 0;

  /// Human-readable name for menus / tabs.
  virtual QString displayName() const = 0;

  /// Optional translation namespace prefix used when looking up tab
  /// strings (e.g. "multi_compare" → "multi_compare.title").
  virtual QString i18nNamespace() const { return {}; }

  /// Optional icon for the new-session menu.
  virtual QIcon icon() const { return {}; }

  /// Build the root widget for this tab. Called once during startup.
  virtual QWidget* createPage(QWidget* parent) = 0;

  /// Lifecycle hooks.
  virtual void onActivated() {}
  virtual void onDeactivated() {}
  virtual void onSessionCreated(const QString& sessionId) { (void)sessionId; }
  virtual void onSessionClosed(const QString& sessionId) { (void)sessionId; }

  /// Drop routing — return true to claim the drop.
  virtual bool acceptsDrop(const QStringList& paths) const {
    (void)paths;
    return false;
  }
  virtual void handleDrop(const QStringList& paths) { (void)paths; }
};

}  // namespace imgsli::contracts
