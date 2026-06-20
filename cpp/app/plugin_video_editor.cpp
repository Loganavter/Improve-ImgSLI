// Phase 5: video editor plugin (skeleton).
//
// The Python video editor (src/plugins/video_editor/) is the biggest
// single subsystem in the project — timeline keyframing, multi-track
// composition, ffmpeg orchestration. None of that ports in one shot.
// This file establishes the registration surface so the plugin appears
// in the registry, and exposes a single placeholder service that
// returns the current backend identifier. Deeper porting lands as
// follow-up commits.

#include <QString>
#include <QVariant>
#include <QVariantMap>

#include "imgsli/contracts/plugin_contract.h"
#include "plugin_registry.h"

namespace imgsli::app {
namespace {

class VideoEditorPlugin final : public imgsli::contracts::PluginContract {
 public:
  QString pluginId() const override {
    return QStringLiteral("video_editor");
  }
  QString displayName() const override {
    return QStringLiteral("Video Editor");
  }

  imgsli::contracts::PluginDefinition definition() const override {
    imgsli::contracts::PluginDefinition def;
    def.id = pluginId();
    def.commandIds = {QStringLiteral("video_editor.export_segment")};
    def.translationNamespaces = {QStringLiteral("video_editor")};
    def.metadata.insert(QStringLiteral("status"),
                        QStringLiteral("skeleton"));
    return def;
  }

  bool providesService(const QString& serviceId) const override {
    return serviceId == QStringLiteral("video_editor.backend");
  }

  QVariant callService(const QString& serviceId,
                       const QVariantMap&) override {
    if (serviceId == QStringLiteral("video_editor.backend")) {
      return QStringLiteral("ffmpeg-cli");
    }
    return {};
  }
};

IMGSLI_REGISTER_PLUGIN(VideoEditorPlugin);

}  // namespace
}  // namespace imgsli::app
