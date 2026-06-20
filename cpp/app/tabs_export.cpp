// Phase 4 skeleton: registers the export tab. Full plugin port lands in
// Phase 5.

#include <QLabel>
#include <QVBoxLayout>
#include <QWidget>

#include "i18n_helper.h"
#include "imgsli/contracts/tab_contract.h"
#include "tab_registry.h"

namespace imgsli::app {
namespace {

class ExportTab final : public imgsli::contracts::TabContract {
 public:
  QString sessionType() const override { return QStringLiteral("export"); }

  QString displayName() const override {
    return imgsli::app::tr(QStringLiteral("export.title"));
  }

  QString i18nNamespace() const override { return QStringLiteral("export"); }

  QWidget* createPage(QWidget* parent) override {
    auto* root = new QWidget(parent);
    auto* layout = new QVBoxLayout(root);
    auto* label = new QLabel(
        imgsli::app::tr(QStringLiteral("export.placeholder")));
    label->setAlignment(Qt::AlignCenter);
    label->setWordWrap(true);
    layout->addStretch();
    layout->addWidget(label);
    layout->addStretch();
    return root;
  }
};

IMGSLI_REGISTER_TAB(ExportTab);

}  // namespace
}  // namespace imgsli::app
