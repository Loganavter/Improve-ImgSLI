// Phase 4 skeleton: registers the multi-compare tab. The Python source
// in src/tabs/multi_compare/ is large; the C++ port lands in Phase 5.
// Until then this stub exists so the workspace shell has something to
// switch to and the registry contract is exercised in tests.

#include <QLabel>
#include <QVBoxLayout>
#include <QWidget>

#include "i18n_helper.h"
#include "imgsli/contracts/tab_contract.h"
#include "tab_registry.h"

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

  QWidget* createPage(QWidget* parent) override {
    auto* root = new QWidget(parent);
    auto* layout = new QVBoxLayout(root);
    auto* label = new QLabel(imgsli::app::tr(
        QStringLiteral("multi_compare.placeholder")));
    label->setAlignment(Qt::AlignCenter);
    label->setWordWrap(true);
    layout->addStretch();
    layout->addWidget(label);
    layout->addStretch();
    return root;
  }
};

IMGSLI_REGISTER_TAB(MultiCompareTab);

}  // namespace
}  // namespace imgsli::app
