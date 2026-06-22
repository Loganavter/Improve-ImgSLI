#include "shared/rendering/plan_builder.h"

#include "imgsli_core_bridge/bridge.h"

#include <QByteArray>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>

namespace imgsli::app::shared::rendering {

namespace {

QString rsToQString(const rust::String& value) {
  return QString::fromUtf8(value.data(), static_cast<int>(value.size()));
}

std::string toStdString(const QString& s) {
  const QByteArray utf8 = s.toUtf8();
  return std::string(utf8.constData(), static_cast<std::size_t>(utf8.size()));
}

::imgsli::CanvasPlanInputs toFfiInputs(const PlanInputs& inputs) {
  ::imgsli::CanvasPlanInputs ffi{};
  ffi.left_key = toStdString(inputs.leftKey);
  ffi.right_key = toStdString(inputs.rightKey);
  ffi.canvas_width = static_cast<std::uint32_t>(std::max(1, inputs.canvasWidth));
  ffi.canvas_height = static_cast<std::uint32_t>(std::max(1, inputs.canvasHeight));
  ffi.split = inputs.split;
  ffi.horizontal = inputs.horizontal;
  ffi.divider_enabled = inputs.divider.enabled;
  ffi.divider_thickness = inputs.divider.thickness;
  ffi.capture_x = inputs.magnifier.captureX;
  ffi.capture_y = inputs.magnifier.captureY;
  ffi.magnifier_x = inputs.magnifier.magnifierX;
  ffi.magnifier_y = inputs.magnifier.magnifierY;
  ffi.magnifier_radius = inputs.magnifier.radius;
  ffi.magnifier_zoom = inputs.magnifier.zoom;
  ffi.feature_magnifier = inputs.features.magnifier;
  ffi.feature_guides = inputs.features.guides;
  ffi.feature_capture = inputs.features.capture;
  ffi.feature_filename = inputs.features.filename;
  ffi.feature_paste_overlay = inputs.features.pasteOverlay;
  ffi.left_label = toStdString(inputs.leftLabel);
  ffi.right_label = toStdString(inputs.rightLabel);
  ffi.fill_r = static_cast<std::uint8_t>(inputs.fill.red());
  ffi.fill_g = static_cast<std::uint8_t>(inputs.fill.green());
  ffi.fill_b = static_cast<std::uint8_t>(inputs.fill.blue());
  ffi.fill_a = static_cast<std::uint8_t>(inputs.fill.alpha());
  if (inputs.overlay.has_value()) {
    const auto& o = *inputs.overlay;
    ffi.overlay_enabled = true;
    ffi.overlay_has_border_color = o.borderColor.has_value();
    if (o.borderColor.has_value()) {
      ffi.overlay_border_r = static_cast<std::uint8_t>(o.borderColor->red());
      ffi.overlay_border_g = static_cast<std::uint8_t>(o.borderColor->green());
      ffi.overlay_border_b = static_cast<std::uint8_t>(o.borderColor->blue());
      ffi.overlay_border_a = static_cast<std::uint8_t>(o.borderColor->alpha());
    }
    ffi.overlay_border_width = o.borderWidth;
    ffi.overlay_channel_mode = o.channelMode;
    ffi.overlay_diff_mode = o.diffMode;
    ffi.overlay_interp_mode = o.interpMode;
  } else {
    ffi.overlay_enabled = false;
    ffi.overlay_has_border_color = false;
    ffi.overlay_border_r = 0;
    ffi.overlay_border_g = 0;
    ffi.overlay_border_b = 0;
    ffi.overlay_border_a = 0;
    ffi.overlay_border_width = 0.0F;
    ffi.overlay_channel_mode = 0;
    ffi.overlay_diff_mode = 0;
    ffi.overlay_interp_mode = 1;
  }
  return ffi;
}

QColor jsonRgbaToColor(const QJsonValue& value, QColor fallback) {
  if (!value.isObject()) {
    return fallback;
  }
  const QJsonObject obj = value.toObject();
  return QColor(obj.value(QStringLiteral("r")).toInt(),
                obj.value(QStringLiteral("g")).toInt(),
                obj.value(QStringLiteral("b")).toInt(),
                obj.value(QStringLiteral("a")).toInt(255));
}

std::array<float, 4> jsonArray4(const QJsonValue& value,
                                const std::array<float, 4>& fallback) {
  if (!value.isArray()) {
    return fallback;
  }
  const QJsonArray arr = value.toArray();
  if (arr.size() < 4) {
    return fallback;
  }
  return {static_cast<float>(arr.at(0).toDouble()),
          static_cast<float>(arr.at(1).toDouble()),
          static_cast<float>(arr.at(2).toDouble()),
          static_cast<float>(arr.at(3).toDouble())};
}

OverlayLayoutPlan parseOverlayLayout(const QJsonObject& overlay) {
  OverlayLayoutPlan layout;
  for (const QJsonValue& slotValue :
       overlay.value(QStringLiteral("slots")).toArray()) {
    const QJsonObject s = slotValue.toObject();
    const QJsonObject center = s.value(QStringLiteral("center")).toObject();
    OverlaySlotPlan slot;
    slot.centerX = static_cast<float>(center.value(QStringLiteral("x")).toDouble());
    slot.centerY = static_cast<float>(center.value(QStringLiteral("y")).toDouble());
    slot.radius = static_cast<float>(s.value(QStringLiteral("radius")).toDouble());
    slot.uvRect = jsonArray4(s.value(QStringLiteral("uv_rect")), slot.uvRect);
    slot.uvRect2 = jsonArray4(s.value(QStringLiteral("uv_rect2")), slot.uvRect2);
    slot.source = s.value(QStringLiteral("source")).toInt();
    slot.isCombined = s.value(QStringLiteral("is_combined")).toBool();
    slot.internalSplit =
        static_cast<float>(s.value(QStringLiteral("internal_split")).toDouble());
    slot.horizontal = s.value(QStringLiteral("horizontal")).toBool();
    slot.dividerVisible = s.value(QStringLiteral("divider_visible")).toBool();
    slot.dividerColor =
        jsonArray4(s.value(QStringLiteral("divider_color")), slot.dividerColor);
    slot.dividerThicknessUv = static_cast<float>(
        s.value(QStringLiteral("divider_thickness_uv")).toDouble());
    slot.borderColor =
        jsonRgbaToColor(s.value(QStringLiteral("border_color")), slot.borderColor);
    slot.borderWidth =
        static_cast<float>(s.value(QStringLiteral("border_width")).toDouble());
    layout.overlaySlots.push_back(slot);
  }
  for (const QJsonValue& v :
       overlay.value(QStringLiteral("capture_circles")).toArray()) {
    const QJsonObject c = v.toObject();
    const QJsonObject center = c.value(QStringLiteral("center")).toObject();
    OverlayCapturePlan circle;
    circle.centerX =
        static_cast<float>(center.value(QStringLiteral("x")).toDouble());
    circle.centerY =
        static_cast<float>(center.value(QStringLiteral("y")).toDouble());
    circle.radius =
        static_cast<float>(c.value(QStringLiteral("radius")).toDouble());
    circle.color =
        jsonRgbaToColor(c.value(QStringLiteral("color")), circle.color);
    layout.captureCircles.push_back(circle);
  }
  for (const QJsonValue& v :
       overlay.value(QStringLiteral("guide_sets")).toArray()) {
    const QJsonObject g = v.toObject();
    const QJsonObject center = g.value(QStringLiteral("capture_center")).toObject();
    OverlayGuideSetPlan set;
    set.captureCenterX =
        static_cast<float>(center.value(QStringLiteral("x")).toDouble());
    set.captureCenterY =
        static_cast<float>(center.value(QStringLiteral("y")).toDouble());
    set.captureRadius =
        static_cast<float>(g.value(QStringLiteral("capture_radius")).toDouble());
    for (const QJsonValue& tc :
         g.value(QStringLiteral("target_centers")).toArray()) {
      const QJsonObject p = tc.toObject();
      set.targetCenters.emplace_back(
          static_cast<float>(p.value(QStringLiteral("x")).toDouble()),
          static_cast<float>(p.value(QStringLiteral("y")).toDouble()));
    }
    for (const QJsonValue& tr :
         g.value(QStringLiteral("target_radii")).toArray()) {
      set.targetRadii.push_back(static_cast<float>(tr.toDouble()));
    }
    set.color = jsonRgbaToColor(g.value(QStringLiteral("color")), set.color);
    layout.guideSets.push_back(set);
  }
  if (overlay.contains(QStringLiteral("capture_center"))) {
    const QJsonValue cc = overlay.value(QStringLiteral("capture_center"));
    if (cc.isObject()) {
      const QJsonObject p = cc.toObject();
      layout.captureCenter = std::make_pair(
          static_cast<float>(p.value(QStringLiteral("x")).toDouble()),
          static_cast<float>(p.value(QStringLiteral("y")).toDouble()));
    }
  }
  layout.captureRadius = static_cast<float>(
      overlay.value(QStringLiteral("capture_radius")).toDouble(0.0));
  for (const QJsonValue& v :
       overlay.value(QStringLiteral("overlay_centers")).toArray()) {
    const QJsonArray pair = v.toArray();
    if (pair.size() >= 2) {
      layout.overlayCenters.emplace_back(
          static_cast<float>(pair.at(0).toDouble()),
          static_cast<float>(pair.at(1).toDouble()));
    }
  }
  layout.overlayRadius = static_cast<float>(
      overlay.value(QStringLiteral("overlay_radius")).toDouble(0.0));
  if (overlay.contains(QStringLiteral("border_color")) &&
      !overlay.value(QStringLiteral("border_color")).isNull()) {
    layout.borderColor =
        jsonRgbaToColor(overlay.value(QStringLiteral("border_color")), Qt::white);
  }
  layout.borderWidth = static_cast<float>(
      overlay.value(QStringLiteral("border_width")).toDouble(2.0));
  layout.channelMode = overlay.value(QStringLiteral("channel_mode")).toInt(0);
  layout.diffMode = overlay.value(QStringLiteral("diff_mode")).toInt(0);
  layout.interpMode = overlay.value(QStringLiteral("interp_mode")).toInt(1);
  return layout;
}

CanvasRenderPlan parseFlatFields(const QJsonObject& obj) {
  CanvasRenderPlan plan;
  plan.texture1Id = static_cast<std::uint64_t>(
      obj.value(QStringLiteral("texture1_id")).toDouble());
  plan.texture2Id = static_cast<std::uint64_t>(
      obj.value(QStringLiteral("texture2_id")).toDouble());
  plan.canvasWidth = obj.value(QStringLiteral("canvas_w")).toInt();
  plan.canvasHeight = obj.value(QStringLiteral("canvas_h")).toInt();
  plan.split = static_cast<float>(obj.value(QStringLiteral("split")).toDouble());
  plan.horizontal = obj.value(QStringLiteral("horizontal")).toBool();
  plan.dividerEnabled = obj.value(QStringLiteral("divider_enabled")).toBool();
  plan.dividerThickness = static_cast<float>(
      obj.value(QStringLiteral("divider_thickness")).toDouble());
  plan.magnifierEnabled = obj.value(QStringLiteral("magnifier_enabled")).toBool();
  plan.captureX =
      static_cast<float>(obj.value(QStringLiteral("capture_x")).toDouble());
  plan.captureY =
      static_cast<float>(obj.value(QStringLiteral("capture_y")).toDouble());
  plan.magnifierX =
      static_cast<float>(obj.value(QStringLiteral("magnifier_x")).toDouble());
  plan.magnifierY =
      static_cast<float>(obj.value(QStringLiteral("magnifier_y")).toDouble());
  plan.magnifierRadius = static_cast<float>(
      obj.value(QStringLiteral("magnifier_radius")).toDouble());
  plan.magnifierZoom = static_cast<float>(
      obj.value(QStringLiteral("magnifier_zoom")).toDouble());
  plan.guidesEnabled = obj.value(QStringLiteral("guides_enabled")).toBool();
  plan.captureEnabled = obj.value(QStringLiteral("capture_enabled")).toBool();
  plan.filenameEnabled = obj.value(QStringLiteral("filename_enabled")).toBool();
  plan.pasteOverlayEnabled =
      obj.value(QStringLiteral("paste_overlay_enabled")).toBool();
  plan.leftLabel = obj.value(QStringLiteral("left_label")).toString();
  plan.rightLabel = obj.value(QStringLiteral("right_label")).toString();
  plan.fill = QColor(obj.value(QStringLiteral("fill_r")).toInt(),
                     obj.value(QStringLiteral("fill_g")).toInt(),
                     obj.value(QStringLiteral("fill_b")).toInt(),
                     obj.value(QStringLiteral("fill_a")).toInt(255));
  return plan;
}

QString callJsonBuilder(const ::imgsli::CanvasPlanInputs& ffi) {
  try {
    return rsToQString(::imgsli::build_canvas_render_plan_json(ffi));
  } catch (...) {
    return {};
  }
}

}  // namespace

CanvasRenderPlan buildCanvasRenderPlan(const PlanInputs& inputs) {
  if (!inputs.overlay.has_value()) {
    // Fast path — no rich layout needed, return the flat ffi struct directly.
    const auto ffi = toFfiInputs(inputs);
    const auto plan = ::imgsli::build_canvas_render_plan(ffi);
    return CanvasRenderPlan{
        .texture1Id = plan.texture1_id,
        .texture2Id = plan.texture2_id,
        .canvasWidth = plan.canvas_w,
        .canvasHeight = plan.canvas_h,
        .split = plan.split,
        .horizontal = plan.horizontal,
        .dividerEnabled = plan.divider_enabled,
        .dividerThickness = plan.divider_thickness,
        .magnifierEnabled = plan.magnifier_enabled,
        .captureX = plan.capture_x,
        .captureY = plan.capture_y,
        .magnifierX = plan.magnifier_x,
        .magnifierY = plan.magnifier_y,
        .magnifierRadius = plan.magnifier_radius,
        .magnifierZoom = plan.magnifier_zoom,
        .guidesEnabled = plan.guides_enabled,
        .captureEnabled = plan.capture_enabled,
        .filenameEnabled = plan.filename_enabled,
        .pasteOverlayEnabled = plan.paste_overlay_enabled,
        .leftLabel = rsToQString(plan.left_label),
        .rightLabel = rsToQString(plan.right_label),
        .fill = QColor(plan.fill_r, plan.fill_g, plan.fill_b, plan.fill_a),
    };
  }

  // Rich path — go through the JSON router so we get the overlay layout.
  const QString json = callJsonBuilder(toFfiInputs(inputs));
  if (json.isEmpty()) {
    return {};
  }
  const QJsonDocument doc = QJsonDocument::fromJson(json.toUtf8());
  if (!doc.isObject()) {
    return {};
  }
  const QJsonObject obj = doc.object();
  CanvasRenderPlan plan = parseFlatFields(obj);
  if (obj.contains(QStringLiteral("overlay")) &&
      obj.value(QStringLiteral("overlay")).isObject()) {
    plan.overlayLayout =
        parseOverlayLayout(obj.value(QStringLiteral("overlay")).toObject());
  }
  return plan;
}

QString buildCanvasRenderPlanJson(const PlanInputs& inputs) {
  return callJsonBuilder(toFfiInputs(inputs));
}

}  // namespace imgsli::app::shared::rendering
