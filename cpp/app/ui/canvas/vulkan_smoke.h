// Minimal Vulkan smoke probe.
//
// Two checks:
//   1. QVulkanInstance::create() — does the Vulkan loader work in this env?
//      On the old PySide6 stack this was the failure point under non-xcb
//      (Wayland) sessions; surfacing it explicitly lets us see what works.
//   2. A QRhiWidget with Api::Vulkan, subclassed with empty initialize/render,
//      forces Qt to create a real Vulkan-backed swapchain. If the widget
//      paints at all the backend went up cleanly.
//
// The label above the widget reports the outcome of (1) plus the apiVersion
// and supported extensions reported by Qt.

#pragma once

#include <QDebug>
#include <QGuiApplication>
#include <QLabel>
#include <QRhiWidget>
#include <QString>
#include <QStringList>
#include <QVulkanInstance>
#include <QVBoxLayout>
#include <QWidget>

class EmptyRhiCanvas : public QRhiWidget {
public:
    using QRhiWidget::QRhiWidget;

protected:
    void initialize(QRhiCommandBuffer*) override {}
    void render(QRhiCommandBuffer*) override {}
};

inline QWidget* makeVulkanSmokeBlock(QVulkanInstance& sharedInstance, QWidget* parent) {
    auto* box = new QWidget(parent);
    auto* layout = new QVBoxLayout(box);
    layout->setContentsMargins(0, 0, 0, 0);

    QString report;
    const bool created = sharedInstance.create();
    if (created) {
        const uint32_t api = sharedInstance.apiVersion().majorVersion() << 22
            | sharedInstance.apiVersion().minorVersion() << 12;
        Q_UNUSED(api);
        const QVersionNumber v = sharedInstance.apiVersion();
        QStringList exts;
        for (const QByteArray& e : sharedInstance.extensions()) {
            exts << QString::fromLatin1(e);
        }
        report = QStringLiteral(
            "Vulkan probe:\n"
            "  QVulkanInstance::create() = OK\n"
            "  apiVersion = %1.%2.%3\n"
            "  extensions enabled = %4")
            .arg(v.majorVersion()).arg(v.minorVersion()).arg(v.microVersion())
            .arg(exts.join(QLatin1String(", ")));
    } else {
        report = QStringLiteral(
            "Vulkan probe:\n"
            "  QVulkanInstance::create() FAILED — no usable loader/driver here.\n"
            "  (On the old PySide6 stack this is where non-xcb sessions broke.)");
    }

    layout->addWidget(new QLabel(report, box));

    // QRhiWidget temporarily disabled while we isolate the missing-decoration
    // issue on GNOME Wayland. Re-enable once root cause is found.
    auto* canvas = new EmptyRhiCanvas(box);
    canvas->setApi(QRhiWidget::Api::Vulkan);
    canvas->setMinimumSize(320, 180);
    layout->addWidget(canvas, 1);

    return box;
}
