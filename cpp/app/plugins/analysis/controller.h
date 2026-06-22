#pragma once

#include <QObject>
#include <QString>

namespace imgsli::app {

class ComparisonController;
class Store;

class AnalysisController final : public QObject {
  Q_OBJECT

 public:
  AnalysisController(Store* store, ComparisonController* comparison,
                     QObject* parent = nullptr);

  QString diffMode() const { return diffMode_; }
  QString channelMode() const { return channelMode_; }

 public slots:
  void setDiffMode(const QString& mode);
  void setChannelMode(const QString& mode);
  void calculateMetrics();
  void refresh();

 signals:
  void busyChanged(bool busy);
  void modeChanged(const QString& diffMode, const QString& channelMode);
  void metricsReady(double psnr, double ssim);
  void analysisRendered();
  void errorOccurred(const QString& message);

 private:
  void renderAnalysis();

  Store* store_ = nullptr;
  ComparisonController* comparison_ = nullptr;
  QString diffMode_ = QStringLiteral("off");
  QString channelMode_ = QStringLiteral("RGB");
  int generation_ = 0;
  int activeTasks_ = 0;
};

}  // namespace imgsli::app
