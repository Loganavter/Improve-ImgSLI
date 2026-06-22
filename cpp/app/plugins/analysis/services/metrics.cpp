// Mirrors src/plugins/analysis/services/metrics.py — async PSNR/SSIM
// calculation over the comparison plugin's fitted image pair. The pure
// metric math lives in Rust (`cpp/core/src/plugins/analysis/mod.rs`).

#include <QFutureWatcher>
#include <QImage>
#include <QPair>
#include <QVariant>
#include <QVariantMap>
#include <QtConcurrent>

#include "core/plugin_registry.h"
#include "plugins/analysis/controller.h"
#include "plugins/comparison/controller.h"

namespace imgsli::app {

void AnalysisController::calculateMetrics() {
  if (comparison_ == nullptr) {
    return;
  }
  const QPair<QImage, QImage> pair = comparison_->analysisPair();
  if (pair.first.isNull() || pair.second.isNull()) {
    emit errorOccurred(
        QStringLiteral("Load two images before calculating metrics"));
    return;
  }
  auto* watcher = new QFutureWatcher<QVariant>(this);
  ++activeTasks_;
  emit busyChanged(true);
  connect(watcher, &QFutureWatcher<QVariant>::finished, this,
          [this, watcher]() {
            const QVariantMap result = watcher->result().toMap();
            watcher->deleteLater();
            activeTasks_ = qMax(0, activeTasks_ - 1);
            emit busyChanged(activeTasks_ > 0);
            if (!result.contains(QStringLiteral("psnr")) ||
                !result.contains(QStringLiteral("ssim"))) {
              emit errorOccurred(QStringLiteral("Metric calculation failed"));
              return;
            }
            emit metricsReady(result.value(QStringLiteral("psnr")).toDouble(),
                              result.value(QStringLiteral("ssim")).toDouble());
          });
  watcher->setFuture(QtConcurrent::run([pair]() {
    return PluginRegistry::instance().callService(
        QStringLiteral("analysis.metrics"),
        {{QStringLiteral("left"), pair.first},
         {QStringLiteral("right"), pair.second}});
  }));
}

}  // namespace imgsli::app
