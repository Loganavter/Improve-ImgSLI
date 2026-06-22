#pragma once

#include <QImage>
#include <QObject>
#include <QPair>
#include <QSize>
#include <QString>

namespace imgsli::app {

class CanvasWidget;
class Store;

/// Qt-bound owner of the comparison authoring workflow. Image decoding and
/// state mutations route through plugins/Rust; this class only coordinates
/// Qt widgets, the canvas texture registry, and user-facing status.
class ComparisonController final : public QObject {
  Q_OBJECT

 public:
  explicit ComparisonController(Store* store, CanvasWidget* canvas,
                                QObject* parent = nullptr);

  bool openPair(const QString& leftPath, const QString& rightPath = {});
  void openDialog(QWidget* parent);

  float split() const { return split_; }
  bool horizontal() const { return horizontal_; }
  bool magnifierEnabled() const { return magnifierEnabled_; }
  bool guidesEnabled() const { return guidesEnabled_; }
  bool pasteOverlayEnabled() const { return pasteOverlayEnabled_; }
  QPair<QImage, QImage> analysisPair() const;
  bool hasImagePair() const { return !left_.isNull() && !right_.isNull(); }
  QString leftSourcePath() const { return leftPath_; }
  QString rightSourcePath() const { return rightPath_; }

 public slots:
  void setSplit(float value);
  void setHorizontal(bool enabled);
  void setMagnifierEnabled(bool enabled);
  void setGuidesEnabled(bool enabled);
  void setPasteOverlayEnabled(bool enabled);
  void setAnalysisImage(const QImage& image);
  void setAnalysisImages(const QImage& left, const QImage& right);
  void clearAnalysisImage();

 signals:
  void comparisonChanged();
  void loadingChanged(bool loading);
  void statusChanged(const QString& message);

 private:
  void apply();
  void scheduleScaling(const QSize& canvasSize);
  void applyAnalysisImages();
  static QImage fitImageToCanvas(const QImage& image,
                                 const QSize& canvasSize);
  static QString escapeJsonString(QString value);

  Store* store_ = nullptr;
  CanvasWidget* canvas_ = nullptr;
  QString leftPath_;
  QString rightPath_;
  QImage left_;
  QImage right_;
  QImage fittedLeft_;
  QImage fittedRight_;
  QSize fittedCanvasSize_;
  QImage analysisImage_;
  QImage analysisImage2_;
  float split_ = 0.5F;
  bool horizontal_ = false;
  bool magnifierEnabled_ = true;
  bool guidesEnabled_ = true;
  bool pasteOverlayEnabled_ = false;
  quint64 loadingGeneration_ = 0;
  quint64 scalingGeneration_ = 0;
  bool scalingPending_ = false;
};

}  // namespace imgsli::app
