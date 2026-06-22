#pragma once

#include <QColor>
#include <QHash>
#include <QImage>
#include <QRectF>
#include <QRhiWidget>
#include <QStringList>
#include <QVariant>

#include <array>
#include <cstdint>
#include <memory>
#include <optional>
#include <vector>

class QRhi;
class QMouseEvent;
class QRhiBuffer;
class QRhiCommandBuffer;
class QRhiGraphicsPipeline;
class QRhiSampler;
class QRhiResourceUpdateBatch;
class QRhiShaderResourceBindings;
class QRhiTexture;

namespace imgsli::app {

// Single magnifier slot, mirrored from Rust `OverlaySlot`. `uvRect` /
// `uvRect2` carry the source-1 / source-2 UV regions a split-aware combined
// slot samples.
struct OverlaySlotPlan {
  float centerX = 0.0F;
  float centerY = 0.0F;
  float radius = 0.0F;
  std::array<float, 4> uvRect{0.0F, 0.0F, 1.0F, 1.0F};
  std::array<float, 4> uvRect2{0.0F, 0.0F, 1.0F, 1.0F};
  int source = 0;
  bool isCombined = true;
  float internalSplit = 0.5F;
  bool horizontal = false;
  bool dividerVisible = false;
  std::array<float, 4> dividerColor{1.0F, 1.0F, 1.0F, 1.0F};
  float dividerThicknessUv = 0.0F;
  QColor borderColor = QColor(255, 255, 255, 255);
  float borderWidth = 0.0F;
};

struct OverlayCapturePlan {
  float centerX = 0.0F;
  float centerY = 0.0F;
  float radius = 0.0F;
  QColor color = QColor(255, 255, 255, 255);
};

struct OverlayGuideSetPlan {
  float captureCenterX = 0.0F;
  float captureCenterY = 0.0F;
  float captureRadius = 0.0F;
  std::vector<std::pair<float, float>> targetCenters;
  std::vector<float> targetRadii;
  QColor color = QColor(255, 255, 255, 255);
};

// C++ mirror of Rust `OverlayLayout`. Carried by `CanvasRenderPlan` as an
// optional informational field — the live QRhi renderer keeps consuming the
// flat magnifier/capture/guides fields (which the per-frame feature command
// pipeline mutates), while this rich payload is what non-renderer consumers
// (composition trees, snapshot/replay tools, future multi-cell renderers)
// read. Populated by `shared::rendering::buildCanvasRenderPlan` when the
// caller supplies an `OverlaySpec`.
struct OverlayLayoutPlan {
  std::vector<OverlaySlotPlan> overlaySlots;
  std::vector<OverlayCapturePlan> captureCircles;
  std::vector<OverlayGuideSetPlan> guideSets;
  std::optional<std::pair<float, float>> captureCenter;
  float captureRadius = 0.0F;
  std::vector<std::pair<float, float>> overlayCenters;
  float overlayRadius = 0.0F;
  std::optional<QColor> borderColor;
  float borderWidth = 2.0F;
  int channelMode = 0;
  int diffMode = 0;
  int interpMode = 1;
};

struct CanvasRenderPlan {
  std::uint64_t texture1Id = 0;
  std::uint64_t texture2Id = 0;
  int canvasWidth = 1;
  int canvasHeight = 1;
  float split = 0.5F;
  bool horizontal = false;
  bool dividerEnabled = false;
  float dividerThickness = 2.0F;
  bool magnifierEnabled = false;
  float captureX = 0.35F;
  float captureY = 0.5F;
  float magnifierX = 0.7F;
  float magnifierY = 0.5F;
  float magnifierRadius = 0.16F;
  float magnifierZoom = 2.0F;
  bool guidesEnabled = false;
  bool captureEnabled = false;
  bool filenameEnabled = false;
  bool pasteOverlayEnabled = false;
  QString leftLabel;
  QString rightLabel;
  QColor fill = QColor(37, 37, 37);
  // Optional rich overlay layout. Populated by the shared plan builder when
  // an `OverlaySpec` is supplied; left empty for callers that only need the
  // flat path (current QRhi render). See `OverlayLayoutPlan` doc.
  std::optional<OverlayLayoutPlan> overlayLayout;
};

class RenderPassRegistry;

class CanvasWidget final : public QRhiWidget {
  Q_OBJECT

public:
  explicit CanvasWidget(QWidget *parent = nullptr);
  ~CanvasWidget() override;

  void registerImage(std::uint64_t textureId, const QImage &image);
  void setRenderPlan(const CanvasRenderPlan &plan);
  [[nodiscard]] CanvasRenderPlan renderPlan() const;
  [[nodiscard]] QStringList renderPassNames() const;
  [[nodiscard]] QHash<std::uint64_t, QImage> registeredImages() const;
  bool executeFeatureCommand(const QString &feature, const QString &command,
                             const QVariant &value);

signals:
  void frameRendered();
  void frameRecorded();
  void framesPerSecondMeasured(double fps);

protected:
  void initialize(QRhiCommandBuffer *commandBuffer) override;
  void render(QRhiCommandBuffer *commandBuffer) override;
  void releaseResources() override;
  void mousePressEvent(QMouseEvent *event) override;
  void mouseMoveEvent(QMouseEvent *event) override;
  void mouseReleaseEvent(QMouseEvent *event) override;

private:
  void createPipeline();
  void initializePasses();
  void releaseRhiResources();
  void uploadPendingTextures(QRhiCommandBuffer *commandBuffer);
  void replaceTexture(int index, const QImage &image,
                      QRhiResourceUpdateBatch *updates);
  void rebuildShaderResources();
  [[nodiscard]] QRectF contentViewport() const;

  CanvasRenderPlan plan_;
  QHash<std::uint64_t, QImage> images_;
  std::array<QImage, 2> pendingImages_;
  QRhiBuffer *vertexBuffer_ = nullptr;
  QRhiBuffer *uniformBuffer_ = nullptr;
  std::array<QRhiTexture *, 2> textures_{nullptr, nullptr};
  QRhiSampler *sampler_ = nullptr;
  QRhiShaderResourceBindings *bindings_ = nullptr;
  QRhiGraphicsPipeline *pipeline_ = nullptr;
  std::unique_ptr<RenderPassRegistry> passRegistry_;
  bool frameRenderedEmitted_ = false;
  qint64 fpsWindowStartMs_ = 0;
  int fpsFrameCount_ = 0;
  enum class DragTarget {
    None,
    Divider,
    Magnifier,
  };
  DragTarget dragTarget_ = DragTarget::None;
};

} // namespace imgsli::app

Q_DECLARE_METATYPE(imgsli::app::CanvasRenderPlan)
