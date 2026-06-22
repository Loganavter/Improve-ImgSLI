#pragma once

#include <QJsonObject>
#include <QObject>
#include <QString>

class QProcess;

namespace imgsli::app {

class VideoEditorController final : public QObject {
  Q_OBJECT

 public:
  explicit VideoEditorController(QObject* parent = nullptr);

  QString projectJson() const;
  int timelinePosition() const { return timelinePosition_; }
  int selectionStart() const { return selectionStart_; }
  int selectionEnd() const { return selectionEnd_; }
  bool hasSelection() const { return hasSelection_; }
  bool exporting() const;
  bool keyframeFeatureEnabled(const QString& featureId) const;

 public slots:
  void setResolution(int width, int height);
  void setWidth(int width);
  void setHeight(int height);
  void setFps(int fps);
  void setAspectRatioLocked(bool locked);
  void setContainer(const QString& container);
  void setCodec(const QString& codec);
  void setQualityMode(const QString& mode);
  void setCrf(int crf);
  void setBitrate(const QString& bitrate);
  void setPreset(const QString& preset);
  void setPixelFormat(const QString& pixelFormat);
  void setManualMode(bool enabled);
  void setManualArguments(const QString& arguments);
  void setKeyframeFeatureEnabled(const QString& featureId, bool enabled);

  void seek(int frame);
  void advance(int step = 1);
  void setSelection(int start, int end);
  void clearSelection();

  bool startExport(const QString& input, const QString& output,
                   double startSeconds = -1.0,
                   double durationSeconds = -1.0);
  void cancelExport();

 signals:
  void projectChanged(const QString& json);
  void timelineChanged(int frame);
  void selectionChanged(int start, int end, bool active);
  void exportStarted();
  void exportProgress(int percent);
  void exportLog(const QString& text);
  void exportFinished(bool ok, const QString& message);

 private:
  void emitProject();
  void attachProcess(QProcess* process, double expectedDuration);
  void consumeProgressOutput();

  QJsonObject project_;
  int timelinePosition_ = 0;
  int selectionStart_ = 0;
  int selectionEnd_ = 0;
  bool hasSelection_ = false;
  QProcess* process_ = nullptr;
  QByteArray progressBuffer_;
  double expectedDuration_ = 0.0;
};

}  // namespace imgsli::app
