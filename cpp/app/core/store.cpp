#include "core/store.h"

#include <QByteArray>
#include <QJsonDocument>
#include <QMetaObject>
#include <QThread>

#include <string>

namespace {

QString rsToQString(const rust::String& value) {
    return QString::fromUtf8(value.data(), static_cast<qsizetype>(value.size()));
}

}  // namespace

namespace imgsli::app {

StoreScope StoreScope::settings() {
  return {.kind = Kind::Settings};
}

StoreScope StoreScope::viewport(const QString& tag) {
  return {.kind = Kind::Viewport, .viewportTag = tag};
}

StoreScope StoreScope::document() {
  return {.kind = Kind::Document};
}

StoreScope StoreScope::workspace() {
  return {.kind = Kind::Workspace};
}

StoreScope StoreScope::noOp() {
  return {.kind = Kind::NoOp};
}

StoreScope StoreScope::fromString(const QString& value) {
  if (value == QStringLiteral("settings")) {
    return settings();
  }
  if (value == QStringLiteral("viewport")) {
    return viewport();
  }
  if (value.startsWith(QStringLiteral("viewport."))) {
    return viewport(value.sliced(9));
  }
  if (value == QStringLiteral("document")) {
    return document();
  }
  if (value == QStringLiteral("workspace")) {
    return workspace();
  }
  if (value == QStringLiteral("noop")) {
    return noOp();
  }
  return {};
}

QString StoreScope::toString() const {
  switch (kind) {
    case Kind::Settings:
      return QStringLiteral("settings");
    case Kind::Viewport:
      return viewportTag.isEmpty()
                 ? QStringLiteral("viewport")
                 : QStringLiteral("viewport.%1").arg(viewportTag);
    case Kind::Document:
      return QStringLiteral("document");
    case Kind::Workspace:
      return QStringLiteral("workspace");
    case Kind::NoOp:
      return QStringLiteral("noop");
    case Kind::Unknown:
      return {};
  }
  return {};
}

bool StoreScope::matches(const StoreScope& changed) const {
  if (kind != changed.kind) {
    return false;
  }
  if (kind != Kind::Viewport) {
    return true;
  }
  return viewportTag.isEmpty() || viewportTag == changed.viewportTag;
}

Store::Store(QObject* parent)
    : QObject(parent),
      rustStore_(imgsli::new_store()) {}

QString Store::stateJson() const {
    return rsToQString(imgsli::store_state_json(*rustStore_));
}

bool Store::dispatch(const QString& actionJson) {
    const QByteArray utf8 = actionJson.toUtf8();
    try {
        const auto result = imgsli::store_dispatch(
            *rustStore_,
            *this,
            std::string(utf8.constData(), static_cast<std::size_t>(utf8.size())));
        Q_UNUSED(result);
        return true;
    } catch (const std::exception& ex) {
        emit dispatchFailed(QString::fromUtf8(ex.what()));
        return false;
    }
}

bool Store::setSplitPosition(float value) {
  return dispatch(QString::fromUtf8(
      QJsonDocument(QJsonObject{
                        {QStringLiteral("SetSplitPosition"), value},
                    })
          .toJson(QJsonDocument::Compact)));
}

bool Store::setSplitOrientation(bool horizontal) {
  return dispatch(QString::fromUtf8(
      QJsonDocument(QJsonObject{
                        {QStringLiteral("SetSplitOrientation"),
                         QJsonObject{{QStringLiteral("is_horizontal"),
                                      horizontal}}},
                    })
          .toJson(QJsonDocument::Compact)));
}

bool Store::setDiffMode(const QString& mode) {
  return dispatch(QString::fromUtf8(
      QJsonDocument(QJsonObject{
                        {QStringLiteral("SetDiffMode"), mode},
                    })
          .toJson(QJsonDocument::Compact)));
}

bool Store::setChannelViewMode(const QString& mode) {
  return dispatch(QString::fromUtf8(
      QJsonDocument(QJsonObject{
                        {QStringLiteral("SetChannelViewMode"), mode},
                    })
          .toJson(QJsonDocument::Compact)));
}

bool Store::setCanvasFeature(CanvasFeatureAction action,
                             const QVariant& value) {
  QString actionName;
  switch (action) {
    case CanvasFeatureAction::DividerVisible:
      actionName = QStringLiteral("SetDividerVisible");
      break;
    case CanvasFeatureAction::DividerThickness:
      actionName = QStringLiteral("SetDividerThickness");
      break;
    case CanvasFeatureAction::MagnifierVisible:
      actionName = QStringLiteral("SetMagnifierVisible");
      break;
    case CanvasFeatureAction::MagnifierX:
      actionName = QStringLiteral("SetMagnifierX");
      break;
    case CanvasFeatureAction::MagnifierY:
      actionName = QStringLiteral("SetMagnifierY");
      break;
    case CanvasFeatureAction::MagnifierRadius:
      actionName = QStringLiteral("SetMagnifierRadius");
      break;
    case CanvasFeatureAction::MagnifierZoom:
      actionName = QStringLiteral("SetMagnifierZoom");
      break;
    case CanvasFeatureAction::CaptureVisible:
      actionName = QStringLiteral("SetCaptureVisible");
      break;
    case CanvasFeatureAction::CaptureX:
      actionName = QStringLiteral("SetCaptureX");
      break;
    case CanvasFeatureAction::CaptureY:
      actionName = QStringLiteral("SetCaptureY");
      break;
    case CanvasFeatureAction::GuidesVisible:
      actionName = QStringLiteral("SetGuidesVisible");
      break;
    case CanvasFeatureAction::FilenameOverlayVisible:
      actionName = QStringLiteral("SetFilenameOverlayVisible");
      break;
    case CanvasFeatureAction::FilenameLeft:
      actionName = QStringLiteral("SetFilenameLeft");
      break;
    case CanvasFeatureAction::FilenameRight:
      actionName = QStringLiteral("SetFilenameRight");
      break;
    case CanvasFeatureAction::PasteOverlayVisible:
      actionName = QStringLiteral("SetPasteOverlayVisible");
      break;
  }
  return dispatch(QString::fromUtf8(
      QJsonDocument(QJsonObject{
                        {QStringLiteral("SetCanvasFeature"),
                         QJsonObject{{actionName,
                                      QJsonValue::fromVariant(value)}}},
                    })
          .toJson(QJsonDocument::Compact)));
}

bool Store::createSessionFromBlueprint(const QJsonObject& blueprint,
                                       const QString& title,
                                       bool activate) {
  return dispatch(QString::fromUtf8(
      QJsonDocument(QJsonObject{
                        {QStringLiteral("CreateSessionFromBlueprint"),
                         QJsonObject{
                             {QStringLiteral("title"),
                              title.isEmpty() ? QJsonValue(QJsonValue::Null)
                                              : QJsonValue(title)},
                             {QStringLiteral("blueprint"), blueprint},
                             {QStringLiteral("activate"), activate},
                         }},
                    })
          .toJson(QJsonDocument::Compact)));
}

void Store::on_rust_state_changed(
    rust::String stateJson,
    rust::String scope) {
    const QString state = rsToQString(stateJson);
    const QString changedScope = rsToQString(scope);
    if (QThread::currentThread() == thread()) {
      emit stateChanged(state, changedScope);
      return;
    }
    QMetaObject::invokeMethod(
        this,
        [this, state, changedScope]() {
            emit stateChanged(state, changedScope);
        },
        Qt::QueuedConnection);
}

QMetaObject::Connection Store::subscribe(const StoreScope& scope,
                                         QObject* context,
                                         Subscriber callback) {
  if (context == nullptr || !callback) {
    return {};
  }
  return QObject::connect(
      this, &Store::stateChanged, context,
      [scope, callback = std::move(callback)](const QString& stateJson,
                                               const QString& scopeText) {
        const StoreScope changed = StoreScope::fromString(scopeText);
        if (!scope.matches(changed)) {
          return;
        }
        const QJsonObject state =
            QJsonDocument::fromJson(stateJson.toUtf8()).object();
        QJsonObject payload;
        switch (changed.kind) {
          case StoreScope::Kind::Settings:
            payload = state.value(QStringLiteral("settings")).toObject();
            break;
          case StoreScope::Kind::Viewport:
            payload = state.value(QStringLiteral("viewport")).toObject();
            break;
          case StoreScope::Kind::Document:
            payload = state.value(QStringLiteral("document")).toObject();
            break;
          case StoreScope::Kind::Workspace:
            payload = state.value(QStringLiteral("workspace")).toObject();
            break;
          case StoreScope::Kind::NoOp:
          case StoreScope::Kind::Unknown:
            break;
        }
        callback(StoreUpdate{.scope = changed, .payload = payload});
      });
}

}  // namespace imgsli::app
