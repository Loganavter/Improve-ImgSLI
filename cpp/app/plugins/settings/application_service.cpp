#include "plugins/settings/application_service.h"

#include <QHash>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QString>

#include <exception>
#include <string>

#include "imgsli_core_bridge/bridge.h"
#include "core/store.h"

namespace imgsli::app {

namespace {

QString rs_to_q(const rust::String& s) {
  return QString::fromUtf8(s.data(), static_cast<int>(s.size()));
}

// Map of dialog field → QSettings key. Mirrors the Python
// SettingsManager.save_all_settings keys so existing config files stay
// readable across the port.
const QHash<QString, QString>& settingsKeyTable() {
  static const QHash<QString, QString> table{
      {QStringLiteral("language"), QStringLiteral("language")},
      {QStringLiteral("theme"), QStringLiteral("theme")},
      {QStringLiteral("ui_mode"), QStringLiteral("ui_mode")},
      {QStringLiteral("ui_font_mode"), QStringLiteral("ui_font_mode")},
      {QStringLiteral("ui_font_family"), QStringLiteral("ui_font_family")},
      {QStringLiteral("debug_enabled"), QStringLiteral("debug_mode_enabled")},
      {QStringLiteral("system_notifications_enabled"),
       QStringLiteral("system_notifications_enabled")},
      {QStringLiteral("auto_crop_black_borders"),
       QStringLiteral("auto_crop_black_borders")},
      {QStringLiteral("max_name_length"), QStringLiteral("max_name_length")},
      {QStringLiteral("resolution_limit"),
       QStringLiteral("display_resolution_limit")},
      {QStringLiteral("video_recording_fps"),
       QStringLiteral("video_recording_fps")},
      {QStringLiteral("show_workspace_tabs"),
       QStringLiteral("show_workspace_tabs")},
      {QStringLiteral("rhi_backend"), QStringLiteral("rhi_backend")},
      {QStringLiteral("magnifier_interpolation_method"),
       QStringLiteral("magnifier_movement_interpolation_method")},
      {QStringLiteral("laser_interpolation_method"),
       QStringLiteral("movement_interpolation_method")},
      {QStringLiteral("zoom_interpolation_method"),
       QStringLiteral("zoom_interpolation_method")},
      {QStringLiteral("optimize_magnifier_movement"),
       QStringLiteral("optimize_magnifier_movement")},
      {QStringLiteral("optimize_laser_smoothing"),
       QStringLiteral("optimize_laser_smoothing")},
      {QStringLiteral("magnifier_intersection_highlight_enabled"),
       QStringLiteral("magnifier_intersection_highlight_enabled")},
      {QStringLiteral("magnifier_auto_color_new_instances"),
       QStringLiteral("magnifier_auto_color_new_instances")},
      {QStringLiteral("auto_calculate_psnr"),
       QStringLiteral("auto_calculate_psnr")},
      {QStringLiteral("auto_calculate_ssim"),
       QStringLiteral("auto_calculate_ssim")},
  };
  return table;
}

QString jsonStringValue(const QString& value_json) {
  const QJsonDocument doc = QJsonDocument::fromJson(value_json.toUtf8());
  if (doc.isObject() || doc.isArray()) {
    return value_json;
  }
  const QJsonValue val =
      QJsonDocument::fromJson(QStringLiteral("[%1]").arg(value_json).toUtf8())
          .array()
          .at(0);
  return val.toString();
}

}  // namespace

SettingsApplicationService::SettingsApplicationService(Store* store,
                                                       QSettings* settings,
                                                       QObject* parent)
    : QObject(parent), store_(store), settings_(settings) {}

int SettingsApplicationService::apply(const QString& prev_json,
                                      const QString& next_json) {
  QString rawChanges;
  try {
    const QByteArray prev = prev_json.toUtf8();
    const QByteArray next = next_json.toUtf8();
    rawChanges = rs_to_q(imgsli::settings_dialog_diff_json(
        std::string(prev.constData(),
                    static_cast<std::size_t>(prev.size())),
        std::string(next.constData(),
                    static_cast<std::size_t>(next.size()))));
  } catch (const std::exception& ex) {
    emit applied(0);
    return 0;
  }

  const QJsonArray arr =
      QJsonDocument::fromJson(rawChanges.toUtf8()).array();
  int count = 0;
  for (const QJsonValue& entry : arr) {
    const QJsonObject obj = entry.toObject();
    const QString field = obj.value(QStringLiteral("field")).toString();
    const QString valueJson =
        obj.value(QStringLiteral("value_json")).toString();
    if (field.isEmpty()) {
      continue;
    }
    dispatchForField(field, valueJson);
    persist(field, valueJson);
    ++count;
  }
  emit applied(count);
  return count;
}

void SettingsApplicationService::dispatchForField(const QString& field,
                                                  const QString& value_json) {
  if (store_ == nullptr) {
    return;
  }
  // Only a subset of fields has a typed Rust Action variant today. Remaining
  // fields persist via QSettings and pick up on next launch; typed actions
  // will land alongside their feature ports.
  const QString action = [&]() -> QString {
    if (field == QStringLiteral("theme")) {
      return QStringLiteral(R"({"SetTheme":%1})").arg(value_json);
    }
    if (field == QStringLiteral("language")) {
      return QStringLiteral(R"({"SetLanguage":%1})").arg(value_json);
    }
    if (field == QStringLiteral("ui_mode")) {
      return QStringLiteral(R"({"SetUiMode":%1})").arg(value_json);
    }
    if (field == QStringLiteral("debug_enabled")) {
      return QStringLiteral(R"({"SetDebugMode":%1})").arg(value_json);
    }
    if (field == QStringLiteral("system_notifications_enabled")) {
      return QStringLiteral(R"({"SetSystemNotifications":%1})")
          .arg(value_json);
    }
    if (field == QStringLiteral("auto_crop_black_borders")) {
      return QStringLiteral(R"({"SetAutoCropBlackBorders":%1})")
          .arg(value_json);
    }
    if (field == QStringLiteral("rhi_backend")) {
      return QStringLiteral(R"({"SetRhiBackend":%1})").arg(value_json);
    }
    return {};
  }();
  if (!action.isEmpty()) {
    store_->dispatch(action);
  }
}

void SettingsApplicationService::persist(const QString& field,
                                         const QString& value_json) {
  if (settings_ == nullptr) {
    return;
  }
  const auto& table = settingsKeyTable();
  const auto it = table.find(field);
  if (it == table.end()) {
    return;
  }
  const QJsonValue val =
      QJsonDocument::fromJson(QStringLiteral("[%1]").arg(value_json).toUtf8())
          .array()
          .at(0);
  if (val.isString()) {
    settings_->setValue(it.value(), val.toString());
  } else if (val.isBool()) {
    settings_->setValue(it.value(), val.toBool());
  } else if (val.isDouble()) {
    const double d = val.toDouble();
    const qint64 asInt = static_cast<qint64>(d);
    if (static_cast<double>(asInt) == d) {
      settings_->setValue(it.value(), asInt);
    } else {
      settings_->setValue(it.value(), d);
    }
  } else if (val.isNull()) {
    settings_->remove(it.value());
  } else {
    settings_->setValue(it.value(), value_json);
  }
}

}  // namespace imgsli::app
