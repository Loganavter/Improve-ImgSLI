#pragma once

#include <QStringList>
#include <memory>
#include <vector>

#include "core/render_pass.h"

namespace imgsli::app {

class RenderPassRegistry final {
public:
  void add(std::unique_ptr<CanvasRenderPass> pass);
  void sortByStackingPolicy();
  [[nodiscard]] const std::vector<std::unique_ptr<CanvasRenderPass>> &
  passes() const;
  [[nodiscard]] QStringList names() const;

private:
  std::vector<std::unique_ptr<CanvasRenderPass>> passes_;
};

} // namespace imgsli::app
