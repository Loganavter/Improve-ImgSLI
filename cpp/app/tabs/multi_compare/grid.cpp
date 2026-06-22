#include "tabs/multi_compare/grid.h"

#include <QGridLayout>
#include <QImage>
#include <QPainter>
#include <QVariantList>
#include <QVariantMap>

#include <algorithm>

#include "shared/rendering/plan_builder.h"
#include "ui/canvas/canvas_widget.h"
#include "core/plugin_registry.h"

namespace imgsli::app {
namespace {

constexpr std::uint64_t kCellTextureBase = 4096;

std::uint64_t cellTextureId(int cellIndex, int slot) {
  return kCellTextureBase + static_cast<std::uint64_t>(cellIndex) * 2 +
         static_cast<std::uint64_t>(slot);
}

}  // namespace

MultiCompareGrid::MultiCompareGrid(int rows, int cols, QWidget* parent)
    : QWidget(parent),
      rows_(std::max(1, rows)),
      cols_(std::max(1, cols)),
      gridLayout_(new QGridLayout(this)) {
  gridLayout_->setSpacing(2);
  gridLayout_->setContentsMargins(2, 2, 2, 2);
  for (int r = 0; r < rows_; ++r) {
    for (int c = 0; c < cols_; ++c) {
      auto* cell = new CanvasWidget(this);
      cell->setMinimumSize(160, 90);
      cells_.append(cell);
      gridLayout_->addWidget(cell, r, c);
    }
  }
}

void MultiCompareGrid::setSharedPlan(float split, bool horizontal,
                                     bool magnifierEnabled,
                                     bool guidesEnabled,
                                     bool pasteOverlayEnabled) {
  split_ = split;
  horizontal_ = horizontal;
  magnifierEnabled_ = magnifierEnabled;
  guidesEnabled_ = guidesEnabled;
  pasteOverlayEnabled_ = pasteOverlayEnabled;
  refreshCells();
}

void MultiCompareGrid::addPair(const QString& left, const QString& right) {
  if (left.isEmpty()) {
    return;
  }
  playlist_.append({left, right.isEmpty() ? left : right});
  refreshCells();
  emit playlistChanged();
}

void MultiCompareGrid::removeAt(int index) {
  if (index < 0 || index >= playlist_.size()) {
    return;
  }
  playlist_.removeAt(index);
  refreshCells();
  emit playlistChanged();
}

void MultiCompareGrid::moveUp(int index) {
  if (index <= 0 || index >= playlist_.size()) {
    return;
  }
  std::swap(playlist_[index], playlist_[index - 1]);
  refreshCells();
  emit playlistChanged();
}

void MultiCompareGrid::moveDown(int index) {
  if (index < 0 || index >= playlist_.size() - 1) {
    return;
  }
  std::swap(playlist_[index], playlist_[index + 1]);
  refreshCells();
  emit playlistChanged();
}

QImage MultiCompareGrid::decodeImage(const QString& path) const {
  if (path.isEmpty()) {
    return {};
  }
  return PluginRegistry::instance()
      .callService(QStringLiteral("export.decode_image"),
                   {{QStringLiteral("path"), path}})
      .value<QImage>();
}

void MultiCompareGrid::refreshCells() {
  for (int i = 0; i < cells_.size(); ++i) {
    auto* cell = cells_[i];
    if (cell == nullptr) {
      continue;
    }
    shared::rendering::PlanInputs inputs;
    inputs.split = split_;
    inputs.horizontal = horizontal_;
    inputs.features.magnifier = magnifierEnabled_;
    inputs.features.capture = magnifierEnabled_;
    inputs.features.guides = guidesEnabled_;
    inputs.features.pasteOverlay = pasteOverlayEnabled_;

    const bool hasEntry = i < playlist_.size();
    if (!hasEntry) {
      cell->setRenderPlan(shared::rendering::buildCanvasRenderPlan(inputs));
      continue;
    }
    const auto& pair = playlist_[i];
    const QImage left = decodeImage(pair.first);
    const QImage right = decodeImage(pair.second);
    if (left.isNull()) {
      cell->setRenderPlan(shared::rendering::buildCanvasRenderPlan(inputs));
      continue;
    }
    // Per-cell texture ids are owned by the grid (the path/size hash from the
    // shared builder is not unique across cells when paths repeat). Keep the
    // builder for plan defaults, then override texture ids and canvas size.
    inputs.leftKey = pair.first;
    inputs.rightKey = pair.second;
    inputs.canvasWidth = left.width();
    inputs.canvasHeight = left.height();
    CanvasRenderPlan plan = shared::rendering::buildCanvasRenderPlan(inputs);
    const std::uint64_t t1 = cellTextureId(i, 0);
    const std::uint64_t t2 = cellTextureId(i, 1);
    cell->registerImage(t1, left);
    cell->registerImage(t2, right.isNull() ? left : right);
    plan.texture1Id = t1;
    plan.texture2Id = t2;
    cell->setRenderPlan(plan);
  }
}

QVariantMap MultiCompareGrid::exportComposite(const QString& path,
                                              int cellWidth, int cellHeight,
                                              const QString& format,
                                              int quality) const {
  QVariantMap result{
      {QStringLiteral("ok"), false},
      {QStringLiteral("path"), path},
  };
  if (path.isEmpty() || cellWidth <= 0 || cellHeight <= 0) {
    result.insert(QStringLiteral("error"),
                  QStringLiteral("invalid output settings"));
    return result;
  }
  const int totalWidth = cellWidth * cols_;
  const int totalHeight = cellHeight * rows_;
  QImage composite(totalWidth, totalHeight, QImage::Format_RGBA8888);
  composite.fill(Qt::transparent);
  QPainter painter(&composite);

  QVariantList requests;
  QVector<int> requestCellIndices;
  for (int i = 0; i < cells_.size(); ++i) {
    auto* cell = cells_[i];
    if (cell == nullptr) continue;
    if (cell->renderPlan().texture1Id == 0) continue;
    requests.append(QVariantMap{
        {QStringLiteral("canvas"), QVariant::fromValue<QObject*>(cell)},
        {QStringLiteral("width"), cellWidth},
        {QStringLiteral("height"), cellHeight},
    });
    requestCellIndices.append(i);
  }

  // One registry call renders every populated cell through the shared hidden
  // CanvasWidget. Empty playlist slots remain transparent.
  const QVariantList tiles =
      PluginRegistry::instance()
          .callService(
              QStringLiteral("offscreen_renderer.render_batch"),
              {{QStringLiteral("requests"), requests}})
          .toList();
  if (tiles.size() != requests.size()) {
    painter.end();
    result.insert(QStringLiteral("error"),
                  QStringLiteral("offscreen batch stopped after %1 of %2 cells")
                      .arg(tiles.size())
                      .arg(requests.size()));
    return result;
  }
  for (int requestIndex = 0; requestIndex < tiles.size(); ++requestIndex) {
    const int i = requestCellIndices[requestIndex];
    const int r = i / cols_;
    const int c = i % cols_;
    const QImage tile = tiles[requestIndex].value<QImage>();
    if (tile.isNull()) {
      painter.end();
      result.insert(QStringLiteral("error"),
                    QStringLiteral("offscreen render failed for cell %1")
                        .arg(i));
      return result;
    }
    painter.drawImage(QRect(c * cellWidth, r * cellHeight, cellWidth,
                            cellHeight),
                      tile);
  }
  painter.end();

  const bool ok =
      PluginRegistry::instance()
          .callService(QStringLiteral("export.save_image"),
                       {{QStringLiteral("path"), path},
                        {QStringLiteral("image"), composite},
                        {QStringLiteral("format"), format},
                        {QStringLiteral("quality"), quality}})
          .toBool();
  result.insert(QStringLiteral("ok"), ok);
  result.insert(QStringLiteral("width"), totalWidth);
  result.insert(QStringLiteral("height"), totalHeight);
  if (!ok) {
    result.insert(QStringLiteral("error"),
                  QStringLiteral("encoder rejected composite"));
  }
  return result;
}

}  // namespace imgsli::app
