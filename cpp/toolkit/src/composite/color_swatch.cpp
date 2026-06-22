#include "sli/toolkit/composite/color_swatch.h"

#include <QColorDialog>

#include "sli/toolkit/buttons/controller.h"
#include "sli/toolkit/buttons/regions.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit {

ColorSwatch::ColorSwatch(QColor color, int size, bool alpha, QWidget* parent)
    : Button(
          Button::Config{
              .size = QSize{size, size},
              .backgroundColor = color,
              .cornerRadius = std::max(0, size / 2),
              .borderColor =
                  Theme::getColor(QStringLiteral("dialog.border")),
          },
          parent),
      color_(color),
      alpha_(alpha) {
  connect(this, &QAbstractButton::clicked, this, &ColorSwatch::openDialog);
  Theme::onThemeChanged(this, [this]() { refreshBorder(); });
}

QColor ColorSwatch::color() const { return QColor(color_); }

void ColorSwatch::setColor(QColor c) {
  if (!c.isValid()) return;
  color_ = QColor(c);

  // Update the _main region's customBgColor via the controller.
  auto* ctrl =
      property("buttonController").value<buttons::ButtonController*>();
  if (ctrl != nullptr) {
    auto regions = ctrl->regions();
    for (auto& r : regions) {
      if (r.id == QStringLiteral("_main")) {
        r.customBgColor = c;
        break;
      }
    }
    // Re-apply via setSpec or setRegions.
    // We need the previous shape/args. Keep it minimal: rebuild from regions.
    buttons::ButtonSpecArgs args;
    args.variant = QStringLiteral("surface");
    args.shape = ctrl->spec().shape;
    ctrl->setRegions(regions, args);
  }
}

void ColorSwatch::refreshBorder() {
  auto* ctrl =
      property("buttonController").value<buttons::ButtonController*>();
  if (ctrl != nullptr) {
    auto regions = ctrl->regions();
    for (auto& r : regions) {
      if (r.id == QStringLiteral("_main")) {
        r.overrideBorderColor =
            QColor(Theme::getColor(QStringLiteral("dialog.border")));
        break;
      }
    }
    buttons::ButtonSpecArgs args;
    args.variant = QStringLiteral("surface");
    args.shape = ctrl->spec().shape;
    ctrl->setRegions(regions, args);
  }
}

void ColorSwatch::openDialog() {
  if (dialog_ && dialog_->isVisible()) {
    dialog_->raise();
    dialog_->activateWindow();
    return;
  }
  auto* parentWindow = window();
  auto* dialog = new QColorDialog(color_, parentWindow);
  if (alpha_) {
    dialog->setOption(QColorDialog::ShowAlphaChannel, true);
  }
  dialog->setModal(false);

  connect(dialog, &QColorDialog::colorSelected, this,
          [this](const QColor& c) {
            if (c.isValid()) {
              setColor(c);
              emit colorChanged(QColor(c));
            }
          });
  connect(dialog, &QDialog::finished, this, [this](int) {
    dialog_.clear();
    clearFocus();
  });
  dialog_ = dialog;
  dialog_->show();
}

}  // namespace sli::toolkit