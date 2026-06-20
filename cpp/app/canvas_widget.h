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
