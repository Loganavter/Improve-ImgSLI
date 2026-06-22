// ComparisonController — bridge between Qt widgets and the Rust store.
//
// Static lifecycle + setters live here. Async decode/scaling live in
// `use_cases/loading.cpp`. The user-facing file-pair picker lives in
// `use_cases/navigation.cpp`. Together they mirror
// `src/plugins/comparison/`.

#include "plugins/comparison/controller.h"

#include <QImage>
#include <QVariantMap>

#include <algorithm>
#include <cstdint>
#include <exception>
#include <string>

#include "core/store.h"
#include "shared/rendering/plan_builder.h"
#include "ui/canvas/canvas_widget.h"

namespace imgsli::app {

ComparisonController::ComparisonController(Store* store, CanvasWidget* canvas,
                                           QObject* parent)
    : QObject(parent), store_(store), canvas_(canvas) {
  if (store_ != nullptr) {
    store_->subscribe(
        StoreScope::viewport(), this,
        [this](const StoreUpdate& update) {
          const QJsonObject viewState =
              update.payload.value(QStringLiteral("view_state")).toObject();
          bool changed = false;
          if (update.scope.viewportTag == QStringLiteral("split")) {
            const float nextSplit = static_cast<float>(
                viewState.value(QStringLiteral("split_position"))
                    .toDouble(split_));
            const bool nextHorizontal =
                viewState.value(QStringLiteral("is_horizontal"))
                    .toBool(horizontal_);
            changed = nextSplit != split_ || nextHorizontal != horizontal_;
            split_ = nextSplit;
            horizontal_ = nextHorizontal;
          }
          if (update.scope.viewportTag == QStringLiteral("feature_state")) {
            const QJsonObject features =
                viewState.value(QStringLiteral("feature_state")).toObject();
            const QJsonObject magnifier =
                features.value(QStringLiteral("magnifier")).toObject();
            const QJsonObject guides =
                features.value(QStringLiteral("guides")).toObject();
            const QJsonObject pasteOverlay =
                features.value(QStringLiteral("paste_overlay")).toObject();
            const bool nextMagnifier =
                magnifier.contains(QStringLiteral("visible"))
                    ? magnifier.value(QStringLiteral("visible")).toBool()
                    : magnifierEnabled_;
            const bool nextGuides =
                guides.contains(QStringLiteral("visible"))
                    ? guides.value(QStringLiteral("visible")).toBool()
                    : guidesEnabled_;
            const bool nextPasteOverlay =
                pasteOverlay.contains(QStringLiteral("visible"))
                    ? pasteOverlay.value(QStringLiteral("visible")).toBool()
                    : pasteOverlayEnabled_;
            changed = changed || nextMagnifier != magnifierEnabled_ ||
                      nextGuides != guidesEnabled_ ||
                      nextPasteOverlay != pasteOverlayEnabled_;
            magnifierEnabled_ = nextMagnifier;
            guidesEnabled_ = nextGuides;
            pasteOverlayEnabled_ = nextPasteOverlay;
          }
          if (changed) {
            apply();
          }
        });
  }
}

void ComparisonController::setSplit(float value) {
  const float clamped = std::clamp(value, 0.0F, 1.0F);
  if (store_ != nullptr) {
    store_->setSplitPosition(clamped);
    return;
  }
  split_ = clamped;
  apply();
}

void ComparisonController::setHorizontal(bool enabled) {
  if (store_ != nullptr) {
    store_->setSplitOrientation(enabled);
    return;
  }
  horizontal_ = enabled;
  apply();
}

void ComparisonController::setMagnifierEnabled(bool enabled) {
  if (store_ != nullptr) {
    store_->setCanvasFeature(CanvasFeatureAction::MagnifierVisible, enabled);
    store_->setCanvasFeature(CanvasFeatureAction::CaptureVisible, enabled);
    return;
  }
  magnifierEnabled_ = enabled;
  apply();
}

void ComparisonController::setGuidesEnabled(bool enabled) {
  if (store_ != nullptr) {
    store_->setCanvasFeature(CanvasFeatureAction::GuidesVisible, enabled);
    return;
  }
  guidesEnabled_ = enabled;
  apply();
}

void ComparisonController::setPasteOverlayEnabled(bool enabled) {
  if (store_ != nullptr) {
    store_->setCanvasFeature(CanvasFeatureAction::PasteOverlayVisible, enabled);
    return;
  }
  pasteOverlayEnabled_ = enabled;
  apply();
}

QPair<QImage, QImage> ComparisonController::analysisPair() const {
  if (left_.isNull() || right_.isNull() || fittedLeft_.isNull() ||
      fittedRight_.isNull()) {
    return {};
  }
  return {fittedLeft_, fittedRight_};
}

void ComparisonController::setAnalysisImage(const QImage& image) {
  analysisImage_ = image.convertToFormat(QImage::Format_RGBA8888);
  analysisImage2_ = analysisImage_;
  applyAnalysisImages();
}

void ComparisonController::setAnalysisImages(const QImage& left,
                                              const QImage& right) {
  analysisImage_ = left.convertToFormat(QImage::Format_RGBA8888);
  analysisImage2_ = right.convertToFormat(QImage::Format_RGBA8888);
  applyAnalysisImages();
}

void ComparisonController::clearAnalysisImage() {
  if (analysisImage_.isNull()) {
    return;
  }
  analysisImage_ = {};
  analysisImage2_ = {};
  apply();
}

void ComparisonController::apply() {
  if (left_.isNull() || canvas_ == nullptr) {
    return;
  }
  try {
    const QImage right = right_.isNull() ? left_ : right_;
    const QString rightPath = rightPath_.isEmpty() ? leftPath_ : rightPath_;
    const QSize canvasSize(qMax(left_.width(), right.width()),
                            qMax(left_.height(), right.height()));
    if (fittedCanvasSize_ != canvasSize || fittedLeft_.isNull() ||
        fittedRight_.isNull()) {
      scheduleScaling(canvasSize);
      return;
    }
    shared::rendering::PlanInputs inputs;
    inputs.leftKey = leftPath_;
    inputs.rightKey = rightPath;
    inputs.canvasWidth = canvasSize.width();
    inputs.canvasHeight = canvasSize.height();
    inputs.split = split_;
    inputs.horizontal = horizontal_;
    inputs.features.magnifier = magnifierEnabled_;
    inputs.features.guides = guidesEnabled_;
    inputs.features.capture = magnifierEnabled_;
    inputs.features.pasteOverlay = pasteOverlayEnabled_;
    // Request the rich overlay layout — non-renderer consumers (composition
    // trees, snapshot/replay tools) read it via `plan.overlayLayout`; the
    // live QRhi render path keeps consuming the flat fields below.
    inputs.overlay = shared::rendering::OverlaySpec{};
    const auto plan = shared::rendering::buildCanvasRenderPlan(inputs);
    canvas_->registerImage(plan.texture1Id, fittedLeft_);
    canvas_->registerImage(plan.texture2Id, fittedRight_);
    canvas_->setRenderPlan(plan);
    if (!analysisImage_.isNull()) {
      applyAnalysisImages();
    }
    if (store_ != nullptr) {
      store_->dispatch(
          QStringLiteral(
              R"({"SetActiveImagePath":{"slot":"Left","path":"%1"}})")
              .arg(escapeJsonString(leftPath_)));
    }
    emit comparisonChanged();
  } catch (const std::exception& ex) {
    const QString message = QString::fromUtf8(ex.what());
    emit statusChanged(message);
    if (store_ != nullptr) {
      emit store_->dispatchFailed(message);
    }
  }
}

QString ComparisonController::escapeJsonString(QString value) {
  value.replace(u'\\', QStringLiteral("\\\\"));
  value.replace(u'"', QStringLiteral("\\\""));
  return value;
}

}  // namespace imgsli::app
