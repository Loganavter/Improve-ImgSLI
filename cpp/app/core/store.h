#pragma once

#include <QJsonObject>
#include <QMetaObject>
#include <QObject>
#include <QString>
#include <QVariant>

#include <functional>

#include "imgsli_core_bridge/bridge.h"

namespace imgsli::app {

struct StoreScope {
  enum class Kind {
    Settings,
    Viewport,
    Document,
    Workspace,
    NoOp,
    Unknown,
  };

  Kind kind = Kind::Unknown;
  QString viewportTag;

  static StoreScope settings();
  static StoreScope viewport(const QString& tag = {});
  static StoreScope document();
  static StoreScope workspace();
  static StoreScope noOp();
  static StoreScope fromString(const QString& value);

  [[nodiscard]] QString toString() const;
  [[nodiscard]] bool matches(const StoreScope& changed) const;
};

struct StoreUpdate {
  StoreScope scope;
  QJsonObject payload;
};

enum class CanvasFeatureAction {
  DividerVisible,
  DividerThickness,
  MagnifierVisible,
  MagnifierX,
  MagnifierY,
  MagnifierRadius,
  MagnifierZoom,
  CaptureVisible,
  CaptureX,
  CaptureY,
  GuidesVisible,
  FilenameOverlayVisible,
  FilenameLeft,
  FilenameRight,
  PasteOverlayVisible,
};

class Store final : public QObject, public imgsli::StoreObserver {
  Q_OBJECT

 public:
  using Subscriber = std::function<void(const StoreUpdate&)>;

  explicit Store(QObject* parent = nullptr);

  [[nodiscard]] QString stateJson() const;
  bool dispatch(const QString& actionJson);
  bool setSplitPosition(float value);
  bool setSplitOrientation(bool horizontal);
  bool setDiffMode(const QString& mode);
  bool setChannelViewMode(const QString& mode);
  bool setCanvasFeature(CanvasFeatureAction action, const QVariant& value);
  bool createSessionFromBlueprint(const QJsonObject& blueprint,
                                  const QString& title = {},
                                  bool activate = true);
  void on_rust_state_changed(rust::String stateJson,
                             rust::String scope) override;

  /// Subscribe to one typed state scope. A viewport scope without a tag
  /// matches every `viewport.*` update; a tagged scope matches only that tag.
  /// The QObject context owns the connection and disconnects automatically.
  QMetaObject::Connection subscribe(const StoreScope& scope, QObject* context,
                                    Subscriber callback);

 signals:
  void stateChanged(const QString& stateJson, const QString& scope);
  void dispatchFailed(const QString& message);

 private:
  rust::Box<imgsli::RustStore> rustStore_;
};

}  // namespace imgsli::app
