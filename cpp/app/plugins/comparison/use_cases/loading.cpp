// Mirrors src/plugins/comparison/use_cases/loading.py — async decode of
// the image pair through the export plugin, fit-to-canvas scaling
// through QtConcurrent, and the analysis-image overlay used by the
// analysis plugin to display its diff/channel result.

#include <QFutureWatcher>
#include <QImage>
#include <QPainter>
#include <QPoint>
#include <QSize>
#include <QString>
#include <QtConcurrent>

#include <cstdint>

#include "core/plugin_registry.h"
#include "core/store.h"
#include "imgsli_core_bridge/bridge.h"
#include "plugins/comparison/controller.h"
#include "ui/canvas/canvas_widget.h"

namespace imgsli::app {
namespace {

struct DecodeResult {
  QImage left;
  QImage right;
  QString errorPath;
};

struct ScaleResult {
  QImage left;
  QImage right;
  QSize canvasSize;
  quint64 generation = 0;
};

}  // namespace

bool ComparisonController::openPair(const QString& leftPath,
                                     const QString& rightPath) {
  if (leftPath.isEmpty()) {
    return false;
  }
  const quint64 generation = ++loadingGeneration_;
  ++scalingGeneration_;
  scalingPending_ = false;
  emit loadingChanged(true);
  emit statusChanged(QStringLiteral("Loading %1").arg(leftPath));

  auto* watcher = new QFutureWatcher<DecodeResult>(this);
  connect(watcher, &QFutureWatcher<DecodeResult>::finished, this,
          [this, watcher, generation, leftPath, rightPath]() {
            const DecodeResult result = watcher->result();
            watcher->deleteLater();
            if (generation != loadingGeneration_) {
              return;
            }
            emit loadingChanged(false);
            if (!result.errorPath.isEmpty()) {
              const QString message =
                  QStringLiteral("Decode failed: %1").arg(result.errorPath);
              emit statusChanged(message);
              if (store_ != nullptr) {
                emit store_->dispatchFailed(message);
              }
              return;
            }
            leftPath_ = leftPath;
            rightPath_ = rightPath;
            left_ = result.left;
            right_ = result.right;
            fittedLeft_ = {};
            fittedRight_ = {};
            fittedCanvasSize_ = {};
            apply();
            emit statusChanged(
                rightPath_.isEmpty()
                    ? QStringLiteral("Loaded %1").arg(leftPath_)
                    : QStringLiteral("Loaded %1 and %2")
                          .arg(leftPath_, rightPath_));
          });
  watcher->setFuture(QtConcurrent::run([leftPath, rightPath]() {
    const auto decode = [](const QString& path) {
      return PluginRegistry::instance()
          .callService(QStringLiteral("export.decode_image"),
                        {{QStringLiteral("path"), path}})
          .value<QImage>();
    };
    DecodeResult result;
    result.left = decode(leftPath);
    if (result.left.isNull()) {
      result.errorPath = leftPath;
      return result;
    }
    if (!rightPath.isEmpty()) {
      result.right = decode(rightPath);
      if (result.right.isNull()) {
        result.errorPath = rightPath;
      }
    }
    return result;
  }));
  return true;
}

void ComparisonController::scheduleScaling(const QSize& canvasSize) {
  if (scalingPending_ || left_.isNull() || !canvasSize.isValid()) {
    return;
  }
  scalingPending_ = true;
  const quint64 generation = ++scalingGeneration_;
  const QImage left = left_;
  const QImage right = right_.isNull() ? left_ : right_;
  auto* watcher = new QFutureWatcher<ScaleResult>(this);
  connect(watcher, &QFutureWatcher<ScaleResult>::finished, this,
          [this, watcher, generation]() {
            const ScaleResult result = watcher->result();
            watcher->deleteLater();
            if (generation != scalingGeneration_) {
              return;
            }
            scalingPending_ = false;
            fittedLeft_ = result.left;
            fittedRight_ = result.right;
            fittedCanvasSize_ = result.canvasSize;
            apply();
          });
  watcher->setFuture(
      QtConcurrent::run([left, right, canvasSize, generation]() {
        return ScaleResult{
            .left = ComparisonController::fitImageToCanvas(left, canvasSize),
            .right = ComparisonController::fitImageToCanvas(right, canvasSize),
            .canvasSize = canvasSize,
            .generation = generation,
        };
      }));
}

void ComparisonController::applyAnalysisImages() {
  if (canvas_ == nullptr || analysisImage_.isNull()) {
    return;
  }
  constexpr std::uint64_t kAnalysisTexture1 = 0xA11A'0000'0000'0001ULL;
  constexpr std::uint64_t kAnalysisTexture2 = 0xA11A'0000'0000'0002ULL;
  canvas_->registerImage(kAnalysisTexture1, analysisImage_);
  canvas_->registerImage(kAnalysisTexture2, analysisImage2_);
  CanvasRenderPlan plan = canvas_->renderPlan();
  plan.texture1Id = kAnalysisTexture1;
  plan.texture2Id = kAnalysisTexture2;
  plan.canvasWidth = analysisImage_.width();
  plan.canvasHeight = analysisImage_.height();
  plan.dividerEnabled = analysisImage_.cacheKey() != analysisImage2_.cacheKey();
  plan.filenameEnabled = false;
  plan.pasteOverlayEnabled = false;
  canvas_->setRenderPlan(plan);
}

QImage ComparisonController::fitImageToCanvas(const QImage& image,
                                                const QSize& canvasSize) {
  QImage result(canvasSize, QImage::Format_RGBA8888);
  result.fill(Qt::transparent);
  const auto layout = imgsli::compute_content_layout(
      canvasSize.width(), canvasSize.height(), image.width(), image.height(),
      false);
  if (layout.content_width <= 0 || layout.content_height <= 0) {
    return result;
  }
  const QImage scaled = image.scaled(
      layout.content_width, layout.content_height, Qt::IgnoreAspectRatio,
      Qt::SmoothTransformation);
  QPainter painter(&result);
  painter.drawImage(QPoint(layout.content_x, layout.content_y), scaled);
  return result;
}

}  // namespace imgsli::app
