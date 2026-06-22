#include "session_blueprint_command.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>

#include "plugins/analysis/controller.h"
#include "plugins/comparison/controller.h"
#include "core/store.h"

namespace imgsli::app::cli {
namespace {

QString resolvedPath(const QDir& base, const QString& path) {
  if (path.isEmpty() || QFileInfo(path).isAbsolute()) {
    return path;
  }
  return base.filePath(path);
}

}  // namespace

bool applySessionBlueprintCommand(Store* store,
                                  ComparisonController* comparison,
                                  AnalysisController* analysis,
                                  const QString& path, QString* error) {
  if (path.isEmpty()) {
    return true;
  }
  QFile file(path);
  if (!file.open(QIODevice::ReadOnly)) {
    *error = QStringLiteral("cannot open session blueprint: %1").arg(path);
    return false;
  }
  QJsonParseError parseError;
  const QJsonDocument document =
      QJsonDocument::fromJson(file.readAll(), &parseError);
  if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
    *error = QStringLiteral("invalid session blueprint JSON: %1")
                 .arg(parseError.errorString());
    return false;
  }
  const QJsonObject blueprint = document.object();
  if (blueprint.value(QStringLiteral("session_type")).toString().isEmpty() ||
      blueprint.value(QStringLiteral("plugin_name")).toString().isEmpty()) {
    *error = QStringLiteral(
        "session blueprint requires session_type and plugin_name");
    return false;
  }
  if (!store->createSessionFromBlueprint(blueprint)) {
    *error = QStringLiteral("session blueprint Store dispatch failed");
    return false;
  }

  const QJsonObject visual =
      blueprint.value(QStringLiteral("comparison")).toObject();
  if (visual.isEmpty()) {
    return true;
  }
  comparison->setHorizontal(
      visual.value(QStringLiteral("horizontal")).toBool(false));
  comparison->setMagnifierEnabled(
      visual.value(QStringLiteral("magnifier")).toBool(true));
  comparison->setGuidesEnabled(
      visual.value(QStringLiteral("guides")).toBool(true));
  comparison->setPasteOverlayEnabled(
      visual.value(QStringLiteral("paste_overlay")).toBool(false));
  if (visual.contains(QStringLiteral("split"))) {
    comparison->setSplit(
        static_cast<float>(visual.value(QStringLiteral("split")).toDouble(0.5)));
  }
  if (visual.contains(QStringLiteral("diff_mode"))) {
    analysis->setDiffMode(
        visual.value(QStringLiteral("diff_mode")).toString());
  }
  if (visual.contains(QStringLiteral("channel_mode"))) {
    analysis->setChannelMode(
        visual.value(QStringLiteral("channel_mode")).toString());
  }

  const QDir base = QFileInfo(path).absoluteDir();
  const QString left = resolvedPath(
      base, visual.value(QStringLiteral("left_path")).toString());
  const QString right = resolvedPath(
      base, visual.value(QStringLiteral("right_path")).toString());
  if (!left.isEmpty() && !comparison->openPair(left, right)) {
    *error = QStringLiteral("session blueprint image pair could not be opened");
    return false;
  }
  return true;
}

}  // namespace imgsli::app::cli
