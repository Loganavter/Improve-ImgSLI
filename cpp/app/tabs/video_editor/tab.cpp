// Video Editor workspace tab.
//
// TabContract impl + a flat composition of five sections. Each section
// builds its widgets in `tabs/video_editor/sections/<name>_section.cpp`,
// mirroring `src/plugins/video_editor/widgets/` and the dialog_sections
// decomposition Python-side.

#include <QLineEdit>
#include <QString>
#include <QStringList>
#include <QVBoxLayout>
#include <QVariantMap>
#include <QWidget>

#include "core/tab_registry.h"
#include "imgsli/contracts/tab_contract.h"
#include "plugins/video_editor/controller.h"
#include "shell/i18n_helper.h"
#include "tabs/video_editor/sections/sections.h"

namespace imgsli::app {
namespace {

class VideoEditorTab final : public imgsli::contracts::TabContract {
 public:
  QString sessionType() const override {
    return QStringLiteral("video_editor");
  }

  QString displayName() const override {
    return imgsli::app::tr(QStringLiteral("video_editor.title"));
  }

  QString i18nNamespace() const override {
    return QStringLiteral("video_editor");
  }

  void bindServices(const QVariantMap& services) override {
    controller_ = qobject_cast<VideoEditorController*>(
        services.value(QStringLiteral("videoEditorController"))
            .value<QObject*>());
  }

  bool acceptsDrop(const QStringList& paths) const override {
    return !paths.isEmpty();
  }

  void handleDrop(const QStringList& paths) override {
    if (!paths.isEmpty() && input_ != nullptr) {
      input_->setText(paths[0]);
    }
  }

  QWidget* createPage(QWidget* parent) override {
    auto* root = new QWidget(parent);
    root->setObjectName(QStringLiteral("videoEditorTab"));
    auto* layout = new QVBoxLayout(root);

    video_editor_sections::PageContext ctx;
    ctx.root = root;
    ctx.layout = layout;
    ctx.controller = controller_;

    video_editor_sections::buildProjectSection(ctx);
    video_editor_sections::buildRecordingSection(ctx);
    video_editor_sections::buildPreviewSection(ctx);
    video_editor_sections::buildTimelineSection(ctx);
    video_editor_sections::buildExportSection(ctx);

    input_ = ctx.input;
    return root;
  }

 private:
  VideoEditorController* controller_ = nullptr;
  QLineEdit* input_ = nullptr;
};

IMGSLI_REGISTER_TAB(VideoEditorTab);

}  // namespace
}  // namespace imgsli::app
