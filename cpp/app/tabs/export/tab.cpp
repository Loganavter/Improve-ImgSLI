#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QFormLayout>
#include <QLabel>
#include <QLineEdit>
#include <QObject>
#include <QStandardPaths>
#include <QVariantMap>
#include <QLabel>
#include <QVBoxLayout>
#include <QWidget>

#include "ui/canvas/canvas_widget.h"
#include "shell/i18n_helper.h"
#include "imgsli/contracts/tab_contract.h"
#include "core/plugin_registry.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/atomic/check_box.h"
#include "sli/toolkit/comboboxes/combo_box.h"
#include "sli/toolkit/atomic/spin_box.h"
#include "core/tab_registry.h"

namespace imgsli::app {
namespace {

class ExportTab final : public imgsli::contracts::TabContract {
 public:
  QString sessionType() const override { return QStringLiteral("export"); }

  QString displayName() const override {
    return imgsli::app::tr(QStringLiteral("export.title"));
  }

  QString i18nNamespace() const override { return QStringLiteral("export"); }

  void bindServices(const QVariantMap& services) override {
    canvas_ = services.value(QStringLiteral("canvas")).value<QObject*>();
  }

  QWidget* createPage(QWidget* parent) override {
    auto* root = new QWidget(parent);
    root->setObjectName(QStringLiteral("exportTab"));
    auto* layout = new QVBoxLayout(root);

    auto* heading =
        new QLabel(imgsli::app::tr(QStringLiteral("export.still_image")),
                   root);
    heading->setObjectName(QStringLiteral("exportHeading"));
    layout->addWidget(heading);

    auto* form = new QFormLayout();
    auto* path = new QLineEdit(defaultOutputPath(), root);
    path->setObjectName(QStringLiteral("exportPath"));
    auto* browse = new sli::toolkit::Button(
        imgsli::app::tr(QStringLiteral("export.browse")),
        sli::toolkit::Button::Variant::Surface, root);
    browse->setObjectName(QStringLiteral("exportBrowse"));
    auto* pathRow = new QWidget(root);
    auto* pathLayout = new QHBoxLayout(pathRow);
    pathLayout->setContentsMargins(0, 0, 0, 0);
    pathLayout->addWidget(path, 1);
    pathLayout->addWidget(browse);
    form->addRow(imgsli::app::tr(QStringLiteral("export.output_file")),
                 pathRow);

    auto* format = new sli::toolkit::ComboBox(root);
    format->setObjectName(QStringLiteral("exportFormat"));
    format->addItems({QStringLiteral("PNG"), QStringLiteral("JPEG"),
                      QStringLiteral("WEBP"), QStringLiteral("BMP"),
                      QStringLiteral("TIFF")});
    form->addRow(imgsli::app::tr(QStringLiteral("export.format")), format);

    auto* quality = new sli::toolkit::SpinBox(root);
    quality->setObjectName(QStringLiteral("exportQuality"));
    quality->setRange(1, 100);
    quality->setValue(95);
    quality->setSuffix(QStringLiteral("%"));
    form->addRow(imgsli::app::tr(QStringLiteral("export.quality")), quality);

    auto* usePlanRes = new sli::toolkit::CheckBox(
        imgsli::app::tr(QStringLiteral("export.use_plan_resolution")), root);
    usePlanRes->setObjectName(QStringLiteral("exportUsePlanResolution"));
    usePlanRes->setChecked(true);
    form->addRow(QString(), usePlanRes);

    auto* width = new sli::toolkit::SpinBox(root);
    width->setObjectName(QStringLiteral("exportWidth"));
    width->setRange(1, 16384);
    width->setValue(canvas_ != nullptr
                        ? std::max(1, qobject_cast<CanvasWidget*>(canvas_)
                                          ->renderPlan().canvasWidth)
                        : 1920);
    width->setSuffix(QStringLiteral(" px"));
    width->setEnabled(false);
    form->addRow(imgsli::app::tr(QStringLiteral("export.width")), width);

    auto* height = new sli::toolkit::SpinBox(root);
    height->setObjectName(QStringLiteral("exportHeight"));
    height->setRange(1, 16384);
    height->setValue(canvas_ != nullptr
                         ? std::max(1, qobject_cast<CanvasWidget*>(canvas_)
                                           ->renderPlan().canvasHeight)
                         : 1080);
    height->setSuffix(QStringLiteral(" px"));
    height->setEnabled(false);
    form->addRow(imgsli::app::tr(QStringLiteral("export.height")), height);

    QObject::connect(usePlanRes, &sli::toolkit::CheckBox::toggled, root,
                     [width, height](bool checked) {
                       width->setEnabled(!checked);
                       height->setEnabled(!checked);
                     });

    layout->addLayout(form);

    auto* save = new sli::toolkit::Button(
        imgsli::app::tr(QStringLiteral("export.save_current_view")),
        sli::toolkit::Button::Variant::Default, root);
    save->setObjectName(QStringLiteral("exportSave"));
    auto* status = new QLabel(root);
    status->setObjectName(QStringLiteral("exportStatus"));
    status->setWordWrap(true);
    layout->addWidget(save);
    layout->addWidget(status);
    layout->addStretch();

    QObject::connect(browse, &sli::toolkit::Button::clicked, root,
                     [root, path, format]() {
                       const QString selected = QFileDialog::getSaveFileName(
                           root,
                           imgsli::app::tr(
                               QStringLiteral("export.select_output_file")),
                           ensureExtension(path->text(),
                                           format->currentText()),
                           formatFilter(format->currentText()));
                       if (!selected.isEmpty()) {
                         path->setText(selected);
                       }
                     });
    QObject::connect(save, &sli::toolkit::Button::clicked, root,
                     [this, path, format, quality, usePlanRes, width,
                      height, status]() {
                       if (canvas_ == nullptr) {
                         status->setText(imgsli::app::tr(
                             QStringLiteral("export.canvas_unavailable")));
                         return;
                       }
                       const QString output =
                           ensureExtension(path->text(), format->currentText());
                       path->setText(output);
                       QVariantMap args{
                           {QStringLiteral("path"), output},
                           {QStringLiteral("canvas"),
                            QVariant::fromValue(canvas_)},
                           {QStringLiteral("format"), format->currentText()},
                           {QStringLiteral("quality"), quality->value()},
                       };
                       if (usePlanRes->isChecked()) {
                         args.insert(QStringLiteral("source_resolution"), true);
                       } else {
                         args.insert(QStringLiteral("width"), width->value());
                         args.insert(QStringLiteral("height"), height->value());
                       }
                       const QVariant response =
                           PluginRegistry::instance().callService(
                               QStringLiteral("export.save_canvas"), args);
                       const QVariantMap result = response.toMap();
                       if (result.value(QStringLiteral("ok")).toBool()) {
                         status->setText(
                             imgsli::app::tr(
                                 QStringLiteral("export.saved_status"))
                                 .arg(result
                                          .value(QStringLiteral("width"))
                                          .toInt())
                                 .arg(result
                                          .value(QStringLiteral("height"))
                                          .toInt())
                                 .arg(output));
                       } else {
                         status->setText(
                             imgsli::app::tr(
                                 QStringLiteral("export.failed_status"))
                                 .arg(result
                                          .value(QStringLiteral("error"))
                                          .toString()));
                       }
                     });
    return root;
  }

 private:
  static QString defaultOutputPath() {
    QString directory =
        QStandardPaths::writableLocation(QStandardPaths::PicturesLocation);
    if (directory.isEmpty()) {
      directory = QDir::homePath();
    }
    return QDir(directory).filePath(QStringLiteral("imgsli-comparison.png"));
  }

  static QString extensionFor(const QString& format) {
    const QString normalized = format.toLower();
    return normalized == QStringLiteral("jpeg") ? QStringLiteral("jpg")
                                                 : normalized;
  }

  static QString ensureExtension(const QString& path, const QString& format) {
    const QString extension = extensionFor(format);
    if (path.isEmpty()) {
      return defaultOutputPath();
    }
    QFileInfo info(path);
    if (info.suffix().compare(extension, Qt::CaseInsensitive) == 0 ||
        (format == QStringLiteral("JPEG") &&
         info.suffix().compare(QStringLiteral("jpeg"),
                               Qt::CaseInsensitive) == 0)) {
      return path;
    }
    QString base = path;
    if (!info.suffix().isEmpty()) {
      base.chop(info.suffix().size() + 1);
    }
    return base + QStringLiteral(".") + extension;
  }

  static QString formatFilter(const QString& format) {
    const QString extension = extensionFor(format);
    return QStringLiteral("%1 (*.%2);;%3 (*)")
        .arg(format, extension,
             imgsli::app::tr(QStringLiteral("export.all_files")));
  }

  QObject* canvas_ = nullptr;
};

IMGSLI_REGISTER_TAB(ExportTab);

}  // namespace
}  // namespace imgsli::app
