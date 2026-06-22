#include <QFormLayout>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QPair>
#include <QString>
#include <QStringList>
#include <QVBoxLayout>
#include <QVector>
#include <QWidget>

#include "shell/i18n_helper.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/atomic/check_box.h"
#include "sli/toolkit/comboboxes/combo_box.h"
#include "sli/toolkit/atomic/divider.h"
#include "sli/toolkit/atomic/section_header.h"
#include "sli/toolkit/atomic/spin_box.h"
#include "tabs/video_editor/sections/sections.h"

namespace imgsli::app::video_editor_sections {

void buildProjectSection(PageContext& ctx) {
  using imgsli::app::tr;
  QWidget* root = ctx.root;
  QVBoxLayout* layout = ctx.layout;

  layout->addWidget(new sli::toolkit::SectionHeader(
      tr(QStringLiteral("video_editor.section_project")),
      tr(QStringLiteral("video_editor.section_project_description")), root));
  auto* projectForm = new QFormLayout();
  auto* resolutionRow = new QWidget(root);
  auto* resolutionLayout = new QHBoxLayout(resolutionRow);
  resolutionLayout->setContentsMargins(0, 0, 0, 0);
  ctx.width = makeSpin(root, QStringLiteral("videoWidth"), 2, 16384, 1920);
  ctx.height = makeSpin(root, QStringLiteral("videoHeight"), 2, 16384, 1080);
  resolutionLayout->addWidget(ctx.width);
  resolutionLayout->addWidget(new QLabel(QStringLiteral("×"), resolutionRow));
  resolutionLayout->addWidget(ctx.height);
  projectForm->addRow(tr(QStringLiteral("video_editor.resolution")),
                       resolutionRow);

  ctx.fps = makeSpin(root, QStringLiteral("videoFps"), 1, 240, 60);
  projectForm->addRow(tr(QStringLiteral("video_editor.fps")), ctx.fps);

  ctx.aspectLock = new sli::toolkit::Button(
      tr(QStringLiteral("video_editor.lock_aspect")),
      sli::toolkit::Button::Variant::Default, root);
  ctx.aspectLock->setObjectName(QStringLiteral("videoAspectLock"));
  ctx.aspectLock->setCheckable(true);
  ctx.aspectLock->setChecked(true);
  projectForm->addRow(QString(), ctx.aspectLock);

  ctx.container = makeCombo(
      root, QStringLiteral("videoContainer"),
      {QStringLiteral("mp4"), QStringLiteral("mkv"), QStringLiteral("webm"),
       QStringLiteral("mov"), QStringLiteral("avi")});
  ctx.codec = makeCombo(root, QStringLiteral("videoCodec"),
                         {QStringLiteral("h264"), QStringLiteral("h265"),
                          QStringLiteral("vp9"), QStringLiteral("av1"),
                          QStringLiteral("prores")});
  ctx.qualityMode = makeCombo(
      root, QStringLiteral("videoQualityMode"),
      {QStringLiteral("crf"), QStringLiteral("bitrate")});
  ctx.crf = makeSpin(root, QStringLiteral("videoCrf"), 0, 51, 23);
  ctx.bitrate = new QLineEdit(QStringLiteral("8000k"), root);
  ctx.bitrate->setObjectName(QStringLiteral("videoBitrate"));
  ctx.preset = makeCombo(
      root, QStringLiteral("videoPreset"),
      {QStringLiteral("ultrafast"), QStringLiteral("veryfast"),
       QStringLiteral("fast"), QStringLiteral("medium"),
       QStringLiteral("slow"), QStringLiteral("veryslow")});
  ctx.preset->setCurrentText(QStringLiteral("medium"));
  projectForm->addRow(tr(QStringLiteral("video_editor.container")),
                       ctx.container);
  projectForm->addRow(tr(QStringLiteral("video_editor.codec")), ctx.codec);
  projectForm->addRow(tr(QStringLiteral("video_editor.quality_mode")),
                       ctx.qualityMode);
  projectForm->addRow(QStringLiteral("CRF"), ctx.crf);
  projectForm->addRow(tr(QStringLiteral("video_editor.bitrate")), ctx.bitrate);
  projectForm->addRow(tr(QStringLiteral("video_editor.preset")), ctx.preset);

  auto* keyframeGrid = new QWidget(root);
  auto* keyframeLayout = new QGridLayout(keyframeGrid);
  keyframeLayout->setContentsMargins(0, 0, 0, 0);
  keyframeLayout->setHorizontalSpacing(12);
  keyframeLayout->setVerticalSpacing(4);
  const QVector<QPair<QString, QString>> keyframeFeatureSpecs{
      {QStringLiteral("split"), QStringLiteral("keyframe_split")},
      {QStringLiteral("divider"), QStringLiteral("keyframe_divider")},
      {QStringLiteral("magnifier"), QStringLiteral("keyframe_magnifier")},
      {QStringLiteral("capture"), QStringLiteral("keyframe_capture")},
      {QStringLiteral("guides"), QStringLiteral("keyframe_guides")},
      {QStringLiteral("filename_overlay"),
       QStringLiteral("keyframe_filename_overlay")},
      {QStringLiteral("paste_overlay"),
       QStringLiteral("keyframe_paste_overlay")},
  };
  ctx.keyframeControls.reserve(keyframeFeatureSpecs.size());
  for (int i = 0; i < keyframeFeatureSpecs.size(); ++i) {
    const auto& [featureId, translationSuffix] = keyframeFeatureSpecs[i];
    auto* control = new sli::toolkit::CheckBox(
        tr(QStringLiteral("video_editor.%1").arg(translationSuffix)),
        keyframeGrid);
    control->setObjectName(QStringLiteral("videoKeyframe_%1").arg(featureId));
    control->setChecked(true);
    keyframeLayout->addWidget(control, i / 2, i % 2);
    ctx.keyframeControls.append({featureId, control});
  }
  projectForm->addRow(tr(QStringLiteral("video_editor.keyframe_features")),
                       keyframeGrid);
  layout->addLayout(projectForm);
  layout->addWidget(new sli::toolkit::Divider(Qt::Horizontal, root));
}

}  // namespace imgsli::app::video_editor_sections
