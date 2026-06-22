// AnalysisController — bridge between Qt widgets and the Rust
// analysis core. Lifecycle, store subscription, and mode setters live
// here. Async metric / diff / channel renders live in
// `services/{metrics,runtime}.cpp`, mirroring `src/plugins/analysis/`.

#include "plugins/analysis/controller.h"

#include <QStringList>
#include <QVariantMap>

#include "core/store.h"
#include "plugins/comparison/controller.h"

namespace imgsli::app {

AnalysisController::AnalysisController(Store* store,
                                       ComparisonController* comparison,
                                       QObject* parent)
    : QObject(parent), store_(store), comparison_(comparison) {
  if (comparison_ != nullptr) {
    connect(comparison_, &ComparisonController::comparisonChanged, this,
            &AnalysisController::refresh);
  }
  if (store_ != nullptr) {
    store_->subscribe(
        StoreScope::viewport(), this, [this](const StoreUpdate& update) {
          const QJsonObject viewState =
              update.payload.value(QStringLiteral("view_state")).toObject();
          const QString nextDiff =
              viewState.value(QStringLiteral("diff_mode")).toString(diffMode_);
          const QString nextChannel =
              viewState.value(QStringLiteral("channel_view_mode"))
                  .toString(channelMode_);
          if (nextDiff == diffMode_ && nextChannel == channelMode_) {
            return;
          }
          diffMode_ = nextDiff;
          channelMode_ = nextChannel;
          emit modeChanged(diffMode_, channelMode_);
          renderAnalysis();
        });
  }
}

void AnalysisController::setDiffMode(const QString& mode) {
  static const QStringList modes{
      QStringLiteral("off"), QStringLiteral("highlight"),
      QStringLiteral("grayscale"), QStringLiteral("edges"),
      QStringLiteral("ssim")};
  const QString normalized =
      modes.contains(mode) ? mode : QStringLiteral("off");
  if (store_ != nullptr) {
    store_->setDiffMode(normalized);
    return;
  }
  diffMode_ = normalized;
  emit modeChanged(diffMode_, channelMode_);
  renderAnalysis();
}

void AnalysisController::setChannelMode(const QString& mode) {
  static const QStringList modes{QStringLiteral("RGB"), QStringLiteral("R"),
                                  QStringLiteral("G"), QStringLiteral("B"),
                                  QStringLiteral("L")};
  const QString normalized =
      modes.contains(mode) ? mode : QStringLiteral("RGB");
  if (store_ != nullptr) {
    store_->setChannelViewMode(normalized);
    return;
  }
  channelMode_ = normalized;
  emit modeChanged(diffMode_, channelMode_);
  renderAnalysis();
}

void AnalysisController::refresh() {
  if (diffMode_ != QStringLiteral("off") ||
      channelMode_ != QStringLiteral("RGB")) {
    renderAnalysis();
  }
}

}  // namespace imgsli::app
