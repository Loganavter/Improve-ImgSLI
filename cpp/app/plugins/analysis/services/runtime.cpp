// Mirrors src/plugins/analysis/services/runtime.py — async diff or
// channel rendering of the fitted comparison pair, pushed back onto
// the comparison plugin's analysis-image overlay. Pure pixel math
// lives in Rust (`cpp/core/src/plugins/analysis/mod.rs`).

#include <QFutureWatcher>
#include <QImage>
#include <QPair>
#include <QVariant>
#include <QVariantList>
#include <QVariantMap>
#include <QtConcurrent>

#include "core/plugin_registry.h"
#include "plugins/analysis/controller.h"
#include "plugins/comparison/controller.h"

namespace imgsli::app {

void AnalysisController::renderAnalysis() {
  if (comparison_ == nullptr) {
    return;
  }
  if (diffMode_ == QStringLiteral("off") &&
      channelMode_ == QStringLiteral("RGB")) {
    ++generation_;
    comparison_->clearAnalysisImage();
    return;
  }
  const QPair<QImage, QImage> pair = comparison_->analysisPair();
  if (pair.first.isNull() || pair.second.isNull()) {
    comparison_->clearAnalysisImage();
    return;
  }
  const int generation = ++generation_;
  const QString diffMode = diffMode_;
  const QString channelMode = channelMode_;
  auto* watcher = new QFutureWatcher<QVariant>(this);
  ++activeTasks_;
  emit busyChanged(true);
  connect(watcher, &QFutureWatcher<QVariant>::finished, this,
          [this, watcher, generation, diffMode, pair]() {
            const QVariant result = watcher->result();
            watcher->deleteLater();
            activeTasks_ = qMax(0, activeTasks_ - 1);
            emit busyChanged(activeTasks_ > 0);
            if (generation != generation_) {
              return;
            }
            if (diffMode != QStringLiteral("off")) {
              const QImage image = result.value<QImage>();
              if (image.isNull()) {
                emit errorOccurred(
                    QStringLiteral("Difference rendering failed"));
              } else {
                comparison_->setAnalysisImage(image);
                emit analysisRendered();
              }
              return;
            }
            const QVariantList channels = result.toList();
            if (channels.size() != 2) {
              emit errorOccurred(QStringLiteral("Channel rendering failed"));
              return;
            }
            comparison_->setAnalysisImages(channels[0].value<QImage>(),
                                            channels[1].value<QImage>());
            emit analysisRendered();
          });
  watcher->setFuture(
      QtConcurrent::run([pair, diffMode, channelMode]() -> QVariant {
        if (diffMode != QStringLiteral("off")) {
          return PluginRegistry::instance().callService(
              QStringLiteral("analysis.diff"),
              {{QStringLiteral("left"), pair.first},
                {QStringLiteral("right"), pair.second},
                {QStringLiteral("mode"), diffMode},
                {QStringLiteral("channel"), channelMode}});
        }
        const QVariant left = PluginRegistry::instance().callService(
            QStringLiteral("analysis.channel"),
            {{QStringLiteral("left"), pair.first},
              {QStringLiteral("channel"), channelMode}});
        const QVariant right = PluginRegistry::instance().callService(
            QStringLiteral("analysis.channel"),
            {{QStringLiteral("left"), pair.second},
              {QStringLiteral("channel"), channelMode}});
        return QVariantList{left, right};
      }));
}

}  // namespace imgsli::app
