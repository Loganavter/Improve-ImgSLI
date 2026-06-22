#include <QLabel>
#include <QSlider>
#include <QString>
#include <QVBoxLayout>
#include <QWidget>

#include "plugins/comparison/controller.h"
#include "shell/i18n_helper.h"
#include "sli/toolkit/buttons/button.h"
#include "tabs/multi_compare/sections/sections.h"

namespace imgsli::app::multi_compare_sections {

void buildComparisonControlsSection(PageContext& ctx) {
  using imgsli::app::tr;
  QWidget* root = ctx.root;
  QVBoxLayout* layout = ctx.layout;
  ComparisonController* controller = ctx.controller;

  auto* open = new sli::toolkit::Button(
      tr(QStringLiteral("multi_compare.open_pair")),
      sli::toolkit::Button::Variant::Surface, root);
  open->setObjectName(QStringLiteral("multiCompareOpen"));
  layout->addWidget(open);

  auto* splitLabel =
      new QLabel(tr(QStringLiteral("multi_compare.split_position")), root);
  auto* split = new QSlider(Qt::Horizontal, root);
  split->setObjectName(QStringLiteral("multiCompareSplit"));
  split->setRange(0, 1000);
  split->setValue(controller != nullptr ? qRound(controller->split() * 1000.0F)
                                         : 500);
  layout->addWidget(splitLabel);
  layout->addWidget(split);

  auto* horizontal = makeToggleButton(
      root, QStringLiteral("multi_compare.horizontal"),
      QStringLiteral("multiCompareHorizontal"),
      controller != nullptr && controller->horizontal());
  auto* magnifier = makeToggleButton(
      root, QStringLiteral("multi_compare.magnifier"),
      QStringLiteral("multiCompareMagnifier"),
      controller == nullptr || controller->magnifierEnabled());
  auto* guides = makeToggleButton(
      root, QStringLiteral("multi_compare.guides"),
      QStringLiteral("multiCompareGuides"),
      controller == nullptr || controller->guidesEnabled());
  auto* paste = makeToggleButton(
      root, QStringLiteral("multi_compare.paste_preview"),
      QStringLiteral("multiComparePaste"),
      controller != nullptr && controller->pasteOverlayEnabled());
  layout->addWidget(horizontal);
  layout->addWidget(magnifier);
  layout->addWidget(guides);
  layout->addWidget(paste);

  if (controller == nullptr) {
    open->setEnabled(false);
    split->setEnabled(false);
    horizontal->setEnabled(false);
    magnifier->setEnabled(false);
    guides->setEnabled(false);
    paste->setEnabled(false);
    return;
  }

  QObject::connect(open, &sli::toolkit::Button::clicked, root,
                    [controller, root]() { controller->openDialog(root); });
  QObject::connect(split, &QSlider::valueChanged, controller,
                    [controller](int value) {
                      controller->setSplit(value / 1000.0F);
                    });
  QObject::connect(horizontal, &sli::toolkit::Button::toggled, controller,
                    &ComparisonController::setHorizontal);
  QObject::connect(magnifier, &sli::toolkit::Button::toggled, controller,
                    &ComparisonController::setMagnifierEnabled);
  QObject::connect(guides, &sli::toolkit::Button::toggled, controller,
                    &ComparisonController::setGuidesEnabled);
  QObject::connect(paste, &sli::toolkit::Button::toggled, controller,
                    &ComparisonController::setPasteOverlayEnabled);
}

}  // namespace imgsli::app::multi_compare_sections
