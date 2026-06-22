#include <QLabel>
#include <QString>
#include <QVBoxLayout>
#include <QWidget>

#include <cmath>

#include "plugins/analysis/controller.h"
#include "plugins/comparison/controller.h"
#include "shell/i18n_helper.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/comboboxes/combo_box.h"
#include "tabs/multi_compare/sections/sections.h"

namespace imgsli::app::multi_compare_sections {

void buildAnalysisControlsSection(PageContext& ctx) {
  using imgsli::app::tr;
  QWidget* root = ctx.root;
  QVBoxLayout* layout = ctx.layout;
  ComparisonController* controller = ctx.controller;
  AnalysisController* analysisController = ctx.analysisController;

  auto* diffMode = new sli::toolkit::ComboBox(root);
  diffMode->setObjectName(QStringLiteral("multiCompareDiffMode"));
  diffMode->addItems({QStringLiteral("off"), QStringLiteral("highlight"),
                       QStringLiteral("grayscale"), QStringLiteral("edges"),
                       QStringLiteral("ssim")});
  auto* channelMode = new sli::toolkit::ComboBox(root);
  channelMode->setObjectName(QStringLiteral("multiCompareChannelMode"));
  channelMode->addItems({QStringLiteral("RGB"), QStringLiteral("R"),
                           QStringLiteral("G"), QStringLiteral("B"),
                           QStringLiteral("L")});
  auto* metrics = new sli::toolkit::Button(
      tr(QStringLiteral("multi_compare.calculate_metrics")),
      sli::toolkit::Button::Variant::Surface, root);
  metrics->setObjectName(QStringLiteral("multiCompareMetrics"));
  auto* metricsResult = new QLabel(root);
  metricsResult->setObjectName(QStringLiteral("multiCompareMetricsResult"));
  layout->addWidget(
      new QLabel(tr(QStringLiteral("multi_compare.diff_mode")), root));
  layout->addWidget(diffMode);
  layout->addWidget(
      new QLabel(tr(QStringLiteral("multi_compare.channel_mode")), root));
  layout->addWidget(channelMode);
  layout->addWidget(metrics);
  layout->addWidget(metricsResult);

  if (controller != nullptr) {
    QObject::connect(controller, &ComparisonController::statusChanged,
                      ctx.status, &QLabel::setText);
  }

  if (analysisController == nullptr) {
    diffMode->setEnabled(false);
    channelMode->setEnabled(false);
    metrics->setEnabled(false);
    return;
  }

  diffMode->setCurrentText(analysisController->diffMode());
  channelMode->setCurrentText(analysisController->channelMode());
  QObject::connect(diffMode, &sli::toolkit::ComboBox::currentTextChanged,
                    analysisController, &AnalysisController::setDiffMode);
  QObject::connect(channelMode, &sli::toolkit::ComboBox::currentTextChanged,
                    analysisController, &AnalysisController::setChannelMode);
  QObject::connect(metrics, &sli::toolkit::Button::clicked, analysisController,
                    &AnalysisController::calculateMetrics);
  QObject::connect(analysisController, &AnalysisController::metricsReady, root,
                    [metricsResult](double psnr, double ssim) {
                      metricsResult->setText(
                          QStringLiteral("PSNR: %1 dB   SSIM: %2")
                              .arg(std::isinf(psnr)
                                       ? QStringLiteral("∞")
                                       : QString::number(psnr, 'f', 3))
                              .arg(QString::number(ssim, 'f', 6)));
                    });
  QObject::connect(analysisController, &AnalysisController::busyChanged,
                    metrics, [metrics](bool busy) {
                      metrics->setEnabled(!busy);
                    });
  QObject::connect(analysisController, &AnalysisController::errorOccurred,
                    metricsResult, &QLabel::setText);
}

}  // namespace imgsli::app::multi_compare_sections
