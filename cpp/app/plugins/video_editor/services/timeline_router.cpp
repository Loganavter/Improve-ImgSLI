#include "plugins/video_editor/services/timeline_router.h"

#include "imgsli_core_bridge/bridge.h"

namespace imgsli::app::video_editor_services {

namespace {

QString rs_to_q(const rust::String& s) {
  return QString::fromUtf8(s.data(), static_cast<int>(s.size()));
}

}  // namespace

std::optional<QVariant> routeTimelineService(const QString& id,
                                              const QVariantMap& args) {
  if (id == QStringLiteral("video_editor.timeline_advance")) {
    const qint64 pos = args.value(QStringLiteral("position")).toLongLong();
    const qint64 step = args.value(QStringLiteral("step"), 1).toLongLong();
    return QVariant::fromValue<qlonglong>(
        imgsli::video_timeline_advance(pos, step));
  }
  if (id == QStringLiteral("video_editor.selection_set")) {
    const bool hasStart = args.contains(QStringLiteral("start"));
    const bool hasEnd = args.contains(QStringLiteral("end"));
    const qint64 start = args.value(QStringLiteral("start"), 0).toLongLong();
    const qint64 end = args.value(QStringLiteral("end"), 0).toLongLong();
    return QVariant{
        rs_to_q(imgsli::video_selection_set_json(start, hasStart, end, hasEnd))};
  }
  return std::nullopt;
}

}  // namespace imgsli::app::video_editor_services
