#include <QHBoxLayout>
#include <QSlider>
#include <QString>
#include <QVBoxLayout>
#include <QWidget>

#include "plugins/video_editor/controller.h"
#include "shell/i18n_helper.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/atomic/divider.h"
#include "sli/toolkit/atomic/section_header.h"
#include "sli/toolkit/atomic/spin_box.h"
#include "tabs/video_editor/sections/sections.h"

namespace imgsli::app::video_editor_sections {

void buildTimelineSection(PageContext& ctx) {
  using imgsli::app::tr;
  QWidget* root = ctx.root;
  QVBoxLayout* layout = ctx.layout;
  VideoEditorController* controller = ctx.controller;

  auto* timelineLabel = new sli::toolkit::SectionHeader(
      tr(QStringLiteral("video_editor.timeline")),
      tr(QStringLiteral("video_editor.section_timeline_description")), root);
  auto* timeline = new QSlider(Qt::Horizontal, root);
  timeline->setObjectName(QStringLiteral("videoTimeline"));
  timeline->setRange(0, 100000);
  auto* timelineButtons = new QWidget(root);
  auto* timelineButtonsLayout = new QHBoxLayout(timelineButtons);
  timelineButtonsLayout->setContentsMargins(0, 0, 0, 0);
  auto* previous =
      makeButton(root, QStringLiteral("video_editor.previous"),
                  QStringLiteral("videoPrevious"));
  auto* next = makeButton(root, QStringLiteral("video_editor.next"),
                           QStringLiteral("videoNext"));
  auto* selectionStart =
      makeSpin(root, QStringLiteral("videoSelectionStart"), 0, 100000, 0);
  auto* selectionEnd =
      makeSpin(root, QStringLiteral("videoSelectionEnd"), 0, 100000, 0);
  auto* setSelection =
      makeButton(root, QStringLiteral("video_editor.set_selection"),
                  QStringLiteral("videoSetSelection"));
  auto* clearSelection =
      makeButton(root, QStringLiteral("video_editor.clear_selection"),
                  QStringLiteral("videoClearSelection"));
  timelineButtonsLayout->addWidget(previous);
  timelineButtonsLayout->addWidget(next);
  timelineButtonsLayout->addWidget(selectionStart);
  timelineButtonsLayout->addWidget(selectionEnd);
  timelineButtonsLayout->addWidget(setSelection);
  timelineButtonsLayout->addWidget(clearSelection);
  layout->addWidget(timelineLabel);
  layout->addWidget(timeline);
  layout->addWidget(timelineButtons);
  layout->addWidget(new sli::toolkit::Divider(Qt::Horizontal, root));

  if (controller == nullptr) {
    return;
  }
  QObject::connect(timeline, &QSlider::valueChanged, controller,
                    &VideoEditorController::seek);
  QObject::connect(previous, &sli::toolkit::Button::clicked, controller,
                    [controller]() { controller->advance(-1); });
  QObject::connect(next, &sli::toolkit::Button::clicked, controller,
                    [controller]() { controller->advance(1); });
  QObject::connect(controller, &VideoEditorController::timelineChanged,
                    timeline, &QSlider::setValue);
  QObject::connect(setSelection, &sli::toolkit::Button::clicked, controller,
                    [controller, selectionStart, selectionEnd]() {
                      controller->setSelection(selectionStart->value(),
                                                selectionEnd->value());
                    });
  QObject::connect(clearSelection, &sli::toolkit::Button::clicked, controller,
                    &VideoEditorController::clearSelection);
}

}  // namespace imgsli::app::video_editor_sections
