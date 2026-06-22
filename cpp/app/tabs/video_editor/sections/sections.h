#pragma once

#include <QPair>
#include <QString>
#include <QStringList>
#include <QVector>

class QLineEdit;
class QPlainTextEdit;
class QProgressBar;
class QSlider;
class QVBoxLayout;
class QWidget;

namespace sli::toolkit {
class Button;
class CheckBox;
class ComboBox;
class SpinBox;
}  // namespace sli::toolkit

namespace imgsli::app {
class VideoEditorController;
class VideoRecorder;
}  // namespace imgsli::app

namespace imgsli::app::video_editor_sections {

// Shared page context every section reads/writes. Mirrors the implicit
// shared locals the original single-function createPage used, but as a
// typed value instead of captures-by-reference across 800 lines.
struct PageContext {
  QWidget* root = nullptr;
  QVBoxLayout* layout = nullptr;
  VideoEditorController* controller = nullptr;
  VideoRecorder* recorder = nullptr;  // populated by buildRecordingSection

  // Project section outputs (consumed by export section + project sync):
  sli::toolkit::SpinBox* width = nullptr;
  sli::toolkit::SpinBox* height = nullptr;
  sli::toolkit::SpinBox* fps = nullptr;
  sli::toolkit::Button* aspectLock = nullptr;
  sli::toolkit::ComboBox* container = nullptr;
  sli::toolkit::ComboBox* codec = nullptr;
  sli::toolkit::ComboBox* qualityMode = nullptr;
  sli::toolkit::SpinBox* crf = nullptr;
  QLineEdit* bitrate = nullptr;
  sli::toolkit::ComboBox* preset = nullptr;
  QVector<QPair<QString, sli::toolkit::CheckBox*>> keyframeControls;

  // Export section output (exposed back to TabContract for drag/drop):
  QLineEdit* input = nullptr;
};

// Shared widget factories so each section file does not redeclare them.
sli::toolkit::SpinBox* makeSpin(QWidget* parent, const QString& objectName,
                                 int minimum, int maximum, int value);
sli::toolkit::ComboBox* makeCombo(QWidget* parent, const QString& objectName,
                                   const QStringList& values);
sli::toolkit::Button* makeButton(QWidget* parent,
                                  const QString& translationKey,
                                  const QString& objectName);

// Section builders. Each appends its widgets to ctx.layout and stores
// any cross-section state on ctx.
void buildProjectSection(PageContext& ctx);
void buildRecordingSection(PageContext& ctx);
void buildPreviewSection(PageContext& ctx);
void buildTimelineSection(PageContext& ctx);
void buildExportSection(PageContext& ctx);

}  // namespace imgsli::app::video_editor_sections
