#include "render_pass_registry.h"

#include <algorithm>

#include "imgsli_core_bridge/bridge.h"

namespace imgsli::app {

void RenderPassRegistry::add(std::unique_ptr<CanvasRenderPass> pass) {
  passes_.push_back(std::move(pass));
}

void RenderPassRegistry::sortByStackingPolicy() {
  std::stable_sort(
      passes_.begin(), passes_.end(), [](const auto &left, const auto &right) {
        const auto leftOrder =
            imgsli::resolve_stack_order(static_cast<int>(left->stackRole()));
        const auto rightOrder =
            imgsli::resolve_stack_order(static_cast<int>(right->stackRole()));
        return std::tie(leftOrder.phase, leftOrder.priority) <
               std::tie(rightOrder.phase, rightOrder.priority);
      });
}

const std::vector<std::unique_ptr<CanvasRenderPass>> &
RenderPassRegistry::passes() const {
  return passes_;
}

QStringList RenderPassRegistry::names() const {
  QStringList result;
  for (const auto &pass : passes_) {
    result.append(pass->name());
  }
  return result;
}

} // namespace imgsli::app
