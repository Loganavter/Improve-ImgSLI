// Multi-compare workspace tab.
//
// TabContract impl + a flat composition of three sections. Each section
// builds its widgets in `tabs/multi_compare/sections/<name>_section.cpp`,
// mirroring `src/tabs/multi_compare/ui/`.

#include <QLabel>
#include <QString>
#include <QStringList>
#include <QVBoxLayout>
#include <QVariantMap>
#include <QWidget>

#include "core/tab_registry.h"
#include "imgsli/contracts/tab_contract.h"
#include "plugins/analysis/controller.h"
#include "plugins/comparison/controller.h"
#include "shell/i18n_helper.h"
#include "tabs/multi_compare/sections/sections.h"

namespace imgsli::app {
namespace {

class MultiCompareTab final : public imgsli::contracts::TabContract {
 public:
  QString sessionType() const override {
    return QStringLiteral("multi_compare");
  }

  QString displayName() const override {
    return imgsli::app::tr(QStringLiteral("multi_compare.title"));
  }

  QString i18nNamespace() const override {
    return QStringLiteral("multi_compare");
  }

  void bindServices(const QVariantMap& services) override {
    controller_ = qobject_cast<ComparisonController*>(
        services.value(QStringLiteral("comparisonController"))
            .value<QObject*>());
    analysisController_ = qobject_cast<AnalysisController*>(
        services.value(QStringLiteral("analysisController")).value<QObject*>());
  }

  bool acceptsDrop(const QStringList& paths) const override {
    return !paths.isEmpty() && controller_ != nullptr;
  }

  void handleDrop(const QStringList& paths) override {
    if (paths.isEmpty() || controller_ == nullptr) {
      return;
    }
    controller_->openPair(paths[0],
                           paths.size() > 1 ? paths[1] : QString());
  }

  QWidget* createPage(QWidget* parent) override {
    auto* root = new QWidget(parent);
    root->setObjectName(QStringLiteral("multiCompareTab"));
    auto* layout = new QVBoxLayout(root);

    multi_compare_sections::PageContext ctx;
    ctx.root = root;
    ctx.layout = layout;
    ctx.controller = controller_;
    ctx.analysisController = analysisController_;
    ctx.status = new QLabel(root);
    ctx.status->setObjectName(QStringLiteral("multiCompareStatus"));
    ctx.status->setWordWrap(true);

    multi_compare_sections::buildComparisonControlsSection(ctx);
    multi_compare_sections::buildAnalysisControlsSection(ctx);
    layout->addWidget(ctx.status);
    multi_compare_sections::buildGridSection(ctx);
    layout->addStretch();

    if (controller_ == nullptr) {
      ctx.status->setText(imgsli::app::tr(
          QStringLiteral("multi_compare.controller_unavailable")));
    }
    return root;
  }

 private:
  ComparisonController* controller_ = nullptr;
  AnalysisController* analysisController_ = nullptr;
};

IMGSLI_REGISTER_TAB(MultiCompareTab);

}  // namespace
}  // namespace imgsli::app
