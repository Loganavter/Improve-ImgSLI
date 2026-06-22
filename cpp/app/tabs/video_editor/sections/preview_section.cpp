#include <QHBoxLayout>
#include <QIcon>
#include <QImage>
#include <QLabel>
#include <QLayoutItem>
#include <QPixmap>
#include <QScrollArea>
#include <QSlider>
#include <QString>
#include <QToolButton>
#include <QVBoxLayout>
#include <QVariantMap>
#include <QWidget>

#include <algorithm>

#include "core/plugin_registry.h"
#include "plugins/video_editor/services/recorder.h"
#include "shell/i18n_helper.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/atomic/divider.h"
#include "sli/toolkit/atomic/section_header.h"
#include "tabs/video_editor/sections/sections.h"

namespace imgsli::app::video_editor_sections {

void buildPreviewSection(PageContext& ctx) {
  using imgsli::app::tr;
  QWidget* root = ctx.root;
  QVBoxLayout* layout = ctx.layout;
  VideoRecorder* recorder = ctx.recorder;

  auto* previewSliderLabel = new sli::toolkit::SectionHeader(
      tr(QStringLiteral("video_editor.preview_label")),
      tr(QStringLiteral("video_editor.section_preview_description")), root);
  auto* previewSlider = new QSlider(Qt::Horizontal, root);
  previewSlider->setObjectName(QStringLiteral("videoPreviewSlider"));
  previewSlider->setRange(0, 0);
  previewSlider->setEnabled(false);
  auto* previewIndex = new QLabel(
      tr(QStringLiteral("video_editor.preview_index")).arg(0).arg(0), root);
  previewIndex->setObjectName(QStringLiteral("videoPreviewIndex"));
  auto* previewLabel = new QLabel(root);
  previewLabel->setObjectName(QStringLiteral("videoPreviewLabel"));
  previewLabel->setMinimumHeight(180);
  previewLabel->setAlignment(Qt::AlignCenter);
  previewLabel->setStyleSheet(
      QStringLiteral("background-color: rgb(20,20,20); color: #888;"));
  previewLabel->setText(tr(QStringLiteral("video_editor.preview_empty")));
  auto* thumbStrip = new QScrollArea(root);
  thumbStrip->setObjectName(QStringLiteral("videoThumbStrip"));
  thumbStrip->setWidgetResizable(true);
  thumbStrip->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
  thumbStrip->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
  thumbStrip->setFixedHeight(78);
  auto* thumbHost = new QWidget(thumbStrip);
  auto* thumbLayout = new QHBoxLayout(thumbHost);
  thumbLayout->setContentsMargins(2, 2, 2, 2);
  thumbLayout->setSpacing(2);
  thumbLayout->addStretch();
  thumbStrip->setWidget(thumbHost);

  auto* editRow = new QWidget(root);
  auto* editRowLayout = new QHBoxLayout(editRow);
  editRowLayout->setContentsMargins(0, 0, 0, 0);
  auto* trimBefore = new sli::toolkit::Button(
      tr(QStringLiteral("video_editor.trim_before")),
      sli::toolkit::Button::Variant::Surface, root);
  auto* trimAfter = new sli::toolkit::Button(
      tr(QStringLiteral("video_editor.trim_after")),
      sli::toolkit::Button::Variant::Surface, root);
  auto* deleteCurrent = new sli::toolkit::Button(
      tr(QStringLiteral("video_editor.delete_current")),
      sli::toolkit::Button::Variant::Surface, root);
  auto* undoBtn = new sli::toolkit::Button(
      tr(QStringLiteral("video_editor.undo")),
      sli::toolkit::Button::Variant::Surface, root);
  auto* redoBtn = new sli::toolkit::Button(
      tr(QStringLiteral("video_editor.redo")),
      sli::toolkit::Button::Variant::Surface, root);
  undoBtn->setEnabled(false);
  redoBtn->setEnabled(false);
  editRowLayout->addWidget(trimBefore);
  editRowLayout->addWidget(trimAfter);
  editRowLayout->addWidget(deleteCurrent);
  editRowLayout->addWidget(undoBtn);
  editRowLayout->addWidget(redoBtn);

  layout->addWidget(previewSliderLabel);
  layout->addWidget(previewSlider);
  layout->addWidget(previewIndex);
  layout->addWidget(previewLabel);
  layout->addWidget(thumbStrip);
  layout->addWidget(editRow);
  layout->addWidget(new sli::toolkit::Divider(Qt::Horizontal, root));

  const auto renderPreviewAt = [previewLabel, previewIndex](int index,
                                                              int total) {
    previewIndex->setText(tr(QStringLiteral("video_editor.preview_index"))
                              .arg(index)
                              .arg(total));
    if (total <= 0 || index < 0 || index >= total) {
      previewLabel->setPixmap({});
      previewLabel->setText(tr(QStringLiteral("video_editor.preview_empty")));
      return;
    }
    const int targetW = std::max(160, previewLabel->width());
    const int targetH = std::max(90, previewLabel->height());
    const QImage img =
        PluginRegistry::instance()
            .callService(QStringLiteral("video_editor.preview_render_frame"),
                          {{QStringLiteral("frame_index"), index},
                           {QStringLiteral("width"), targetW},
                           {QStringLiteral("height"), targetH}})
            .value<QImage>();
    if (img.isNull()) {
      previewLabel->setText(tr(QStringLiteral("video_editor.preview_failed")));
      return;
    }
    previewLabel->setPixmap(QPixmap::fromImage(img));
  };

  const auto clearThumbs = [thumbLayout]() {
    QLayoutItem* item = nullptr;
    while ((item = thumbLayout->takeAt(0)) != nullptr) {
      if (auto* w = item->widget()) {
        w->deleteLater();
      }
      delete item;
    }
    thumbLayout->addStretch();
  };

  const auto rebuildThumbs = [thumbLayout, clearThumbs, root,
                                previewSlider](int total) {
    clearThumbs();
    if (total <= 0) {
      return;
    }
    constexpr int kMaxThumbnails = 200;
    constexpr int kThumbW = 96;
    constexpr int kThumbH = 54;
    const int count = std::min(total, kMaxThumbnails);
    for (int i = 0; i < count; ++i) {
      const QImage img =
          PluginRegistry::instance()
              .callService(
                  QStringLiteral("video_editor.preview_render_frame"),
                  {{QStringLiteral("frame_index"), i},
                   {QStringLiteral("width"), kThumbW},
                   {QStringLiteral("height"), kThumbH}})
              .value<QImage>();
      auto* tb = new QToolButton(root);
      tb->setIconSize(QSize(kThumbW, kThumbH));
      tb->setFixedSize(kThumbW + 6, kThumbH + 6);
      tb->setToolTip(QString::number(i));
      if (!img.isNull()) {
        tb->setIcon(QIcon(QPixmap::fromImage(img)));
      }
      QObject::connect(tb, &QToolButton::clicked, root,
                        [previewSlider, i]() { previewSlider->setValue(i); });
      thumbLayout->insertWidget(thumbLayout->count() - 1, tb);
    }
  };

  if (recorder == nullptr) {
    return;
  }
  QObject::connect(recorder, &VideoRecorder::snapshotCaptured, root,
                    [previewSlider, renderPreviewAt](int count) {
                      const int upper = std::max(0, count - 1);
                      previewSlider->setRange(0, upper);
                      previewSlider->setEnabled(count > 0);
                      if (count > 0) {
                        previewSlider->setValue(upper);
                        renderPreviewAt(upper, count);
                      }
                    });
  QObject::connect(recorder, &VideoRecorder::cleared, root,
                    [previewSlider, renderPreviewAt, clearThumbs]() {
                      previewSlider->setRange(0, 0);
                      previewSlider->setEnabled(false);
                      clearThumbs();
                      renderPreviewAt(0, 0);
                    });
  QObject::connect(previewSlider, &QSlider::valueChanged, root,
                    [recorder, renderPreviewAt](int value) {
                      renderPreviewAt(value, recorder->snapshotCount());
                    });
  const auto refreshUndoRedo = [recorder, undoBtn, redoBtn]() {
    undoBtn->setEnabled(recorder->canUndo() &&
                         recorder->state() == VideoRecorder::State::Idle);
    redoBtn->setEnabled(recorder->canRedo() &&
                         recorder->state() == VideoRecorder::State::Idle);
  };
  QObject::connect(recorder, &VideoRecorder::snapshotCaptured, root,
                    [refreshUndoRedo](int) { refreshUndoRedo(); });
  QObject::connect(recorder, &VideoRecorder::cleared, root, refreshUndoRedo);
  QObject::connect(recorder, &VideoRecorder::stateChanged, root,
                    [recorder, rebuildThumbs, refreshUndoRedo](
                        VideoRecorder::State state) {
                      if (state == VideoRecorder::State::Idle) {
                        rebuildThumbs(recorder->snapshotCount());
                      }
                      refreshUndoRedo();
                    });
  QObject::connect(trimBefore, &sli::toolkit::Button::clicked, root,
                    [previewSlider, recorder, rebuildThumbs]() {
                      const int cur = previewSlider->value();
                      const int last = recorder->snapshotCount() - 1;
                      if (last < 0 || cur <= 0) return;
                      PluginRegistry::instance().callService(
                          QStringLiteral("video_editor.recorder_trim"),
                          {{QStringLiteral("start"), cur},
                            {QStringLiteral("end"), last}});
                      rebuildThumbs(recorder->snapshotCount());
                    });
  QObject::connect(trimAfter, &sli::toolkit::Button::clicked, root,
                    [previewSlider, recorder, rebuildThumbs]() {
                      const int cur = previewSlider->value();
                      if (cur < 0 || cur >= recorder->snapshotCount() - 1)
                        return;
                      PluginRegistry::instance().callService(
                          QStringLiteral("video_editor.recorder_trim"),
                          {{QStringLiteral("start"), 0},
                            {QStringLiteral("end"), cur}});
                      rebuildThumbs(recorder->snapshotCount());
                    });
  QObject::connect(deleteCurrent, &sli::toolkit::Button::clicked, root,
                    [previewSlider, recorder, rebuildThumbs]() {
                      const int cur = previewSlider->value();
                      if (cur < 0 || cur >= recorder->snapshotCount()) return;
                      PluginRegistry::instance().callService(
                          QStringLiteral("video_editor.recorder_delete_at"),
                          {{QStringLiteral("index"), cur}});
                      rebuildThumbs(recorder->snapshotCount());
                    });
  QObject::connect(undoBtn, &sli::toolkit::Button::clicked, root,
                    [recorder, rebuildThumbs]() {
                      PluginRegistry::instance().callService(
                          QStringLiteral("video_editor.recorder_undo"), {});
                      rebuildThumbs(recorder->snapshotCount());
                    });
  QObject::connect(redoBtn, &sli::toolkit::Button::clicked, root,
                    [recorder, rebuildThumbs]() {
                      PluginRegistry::instance().callService(
                          QStringLiteral("video_editor.recorder_redo"), {});
                      rebuildThumbs(recorder->snapshotCount());
                    });
}

}  // namespace imgsli::app::video_editor_sections
