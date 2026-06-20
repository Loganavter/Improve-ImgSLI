// Phase 5: comparison plugin.
//
// Owns the split-image comparison workflow that the smoke shell already
// exercises (open two images → Rust decode → C++ canvas executes a
// Rust-produced render plan). In the Python codebase this lives in
// src/plugins/comparison/. The C++ port keeps the same outer contract —
// commands "open_image" / "set_split" / "set_orientation" — and dispatches
// them through the live Store. Render-plan generation continues to come
// from imgsli_core::bridge::build_compare_render_plan.

#include <QString>
#include <QStringList>
#include <QVariant>
#include <QVariantMap>

#include "imgsli/contracts/plugin_contract.h"
#include "imgsli_core_bridge/bridge.h"
#include "plugin_registry.h"
#include "store.h"

namespace imgsli::app {
namespace {

class ComparisonPlugin final : public imgsli::contracts::PluginContract {
 public:
  QString pluginId() const override { return QStringLiteral("comparison"); }
  QString displayName() const override { return QStringLiteral("Comparison"); }

  imgsli::contracts::PluginDefinition definition() const override {
    imgsli::contracts::PluginDefinition def;
    def.id = pluginId();
    def.commandIds = {
        QStringLiteral("comparison.open"),
        QStringLiteral("comparison.set_split"),
        QStringLiteral("comparison.set_orientation"),
        QStringLiteral("comparison.show_single_image"),
        QStringLiteral("comparison.playlist_remove_at"),
        QStringLiteral("comparison.playlist_reorder"),
        QStringLiteral("comparison.playlist_resolve_cross_move"),
    };
    def.translationNamespaces = {QStringLiteral("comparison")};
    return def;
  }

  void onActivate(Store* store) override { store_ = store; }
  void onDeactivate() override { store_ = nullptr; }

  bool providesService(const QString& serviceId) const override {
    static const QStringList kIds{
        QStringLiteral("comparison.set_split"),
        QStringLiteral("comparison.set_orientation"),
        QStringLiteral("comparison.open_image_path"),
        QStringLiteral("comparison.show_single_image"),
        QStringLiteral("comparison.playlist_remove_at"),
        QStringLiteral("comparison.playlist_reorder"),
        QStringLiteral("comparison.playlist_resolve_cross_move"),
    };
    return kIds.contains(serviceId);
  }

  QVariant callService(const QString& serviceId,
                       const QVariantMap& args) override {
    // Pure-math services don't need the Store.
    if (serviceId == QStringLiteral("comparison.playlist_remove_at")) {
      return imgsli::playlist_remove_at(
          args.value(QStringLiteral("len_before")).toInt(),
          args.value(QStringLiteral("current")).toInt(),
          args.value(QStringLiteral("removed_at")).toInt());
    }
    if (serviceId == QStringLiteral("comparison.playlist_reorder")) {
      return imgsli::playlist_reorder(
          args.value(QStringLiteral("current")).toInt(),
          args.value(QStringLiteral("source")).toInt(),
          args.value(QStringLiteral("dest")).toInt());
    }
    if (serviceId ==
        QStringLiteral("comparison.playlist_resolve_cross_move")) {
      return imgsli::playlist_resolve_cross_move(
          args.value(QStringLiteral("previous_path_match")).toInt(),
          args.value(QStringLiteral("target_len_after_move")).toInt(),
          args.value(QStringLiteral("same_list_and_was_current")).toBool(),
          args.value(QStringLiteral("source_index")).toInt());
    }
    // Store-dependent services from here on.
    if (store_ == nullptr) {
      return false;
    }
    if (serviceId == QStringLiteral("comparison.set_split")) {
      const float value = args.value(QStringLiteral("value")).toFloat();
      return store_->dispatch(
          QStringLiteral(R"({"SetSplitPosition":%1})")
              .arg(static_cast<double>(value)));
    }
    if (serviceId == QStringLiteral("comparison.set_orientation")) {
      const bool horizontal =
          args.value(QStringLiteral("horizontal")).toBool();
      return store_->dispatch(
          QStringLiteral(
              R"({"SetSplitOrientation":{"is_horizontal":%1}})")
              .arg(horizontal ? QStringLiteral("true")
                              : QStringLiteral("false")));
    }
    if (serviceId == QStringLiteral("comparison.open_image_path")) {
      QString path = args.value(QStringLiteral("path")).toString();
      path.replace(u'\\', QStringLiteral("\\\\"));
      path.replace(u'"', QStringLiteral("\\\""));
      QString slot = args.value(QStringLiteral("slot")).toString();
      if (slot.isEmpty()) {
        slot = QStringLiteral("Left");
      }
      return store_->dispatch(
          QStringLiteral(
              R"({"SetActiveImagePath":{"slot":"%1","path":"%2"}})")
              .arg(slot, path));
    }
    if (serviceId == QStringLiteral("comparison.show_single_image")) {
      // image_number ∈ {0,1,2} — 0 disables single-image mode.
      const int image = args.value(QStringLiteral("image")).toInt();
      return store_->dispatch(
          QStringLiteral(R"({"SetShowingSingleImageMode":%1})").arg(image));
    }
    return {};
  }

 private:
  Store* store_ = nullptr;
};

IMGSLI_REGISTER_PLUGIN(ComparisonPlugin);

}  // namespace
}  // namespace imgsli::app
