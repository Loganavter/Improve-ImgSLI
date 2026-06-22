#pragma once

#include <QString>
#include <QVariant>
#include <QVariantMap>

#include <optional>

namespace imgsli::app::video_editor_services {

// Routes pure-logic timeline and selection ids:
//   * video_editor.timeline_advance
//   * video_editor.selection_set
// Returns std::nullopt when the id is not owned by this router.
std::optional<QVariant> routeTimelineService(const QString& id,
                                              const QVariantMap& args);

}  // namespace imgsli::app::video_editor_services
