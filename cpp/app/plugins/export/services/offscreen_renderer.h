#pragma once

#include <QCache>
#include <QImage>
#include <QObject>
#include <QPointer>
#include <QSize>

#include "ui/canvas/canvas_widget.h"

namespace imgsli::app {

/// Shared synchronous QRhi offscreen renderer.
///
/// Export and video preview both need the same hidden CanvasWidget lifecycle.
/// Keeping it here prevents each plugin from creating an independent QRhi
/// surface and gives future batch renderers one serialization point.
class OffscreenRenderer final : public QObject {
  Q_OBJECT

 public:
  explicit OffscreenRenderer(QObject *parent = nullptr);
  ~OffscreenRenderer() override;

  [[nodiscard]] QImage renderCanvas(CanvasWidget *source, const QSize &target);
  [[nodiscard]] QImage renderPlan(CanvasWidget *source,
                                  const CanvasRenderPlan &plan,
                                  const QSize &target);
  [[nodiscard]] CanvasWidget *canvas() const { return canvas_; }
  [[nodiscard]] int cacheSize() const { return cache_.size(); }
  void clearCache() { cache_.clear(); }

 private:
  CanvasWidget *ensureCanvas();
  static QString cacheKey(CanvasWidget *source, const CanvasRenderPlan &plan,
                          const QSize &target);

  QPointer<CanvasWidget> canvas_;
  QCache<QString, QImage> cache_{256 * 1024};  // cost is KiB
  bool renderInProgress_ = false;
};

}  // namespace imgsli::app
