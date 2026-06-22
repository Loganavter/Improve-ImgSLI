#include "sli/toolkit/buttons/button.h"

#include <QEnterEvent>
#include <QEvent>
#include <QFontMetrics>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QPaintEvent>
#include <QResizeEvent>
#include <Qt>

#include <algorithm>

#include <QVariant>
#include <QWheelEvent>

#include "sli/toolkit/buttons/capabilities/capability.h"
#include "sli/toolkit/buttons/capabilities/long_press_capability.h"
#include "sli/toolkit/buttons/capabilities/menu_capability.h"
#include "sli/toolkit/buttons/capabilities/scroll_capability.h"
#include "sli/toolkit/buttons/content/content.h"
#include "sli/toolkit/buttons/controller.h"
#include "sli/toolkit/buttons/draw_context.h"
#include "sli/toolkit/buttons/layers/ripple.h"
#include "sli/toolkit/buttons/painter.h"
#include "sli/toolkit/buttons/variants.h"
#include "sli/toolkit/theme.h"

Q_DECLARE_METATYPE(sli::toolkit::buttons::ButtonController*)

namespace sli::toolkit {

namespace {

QString variantNameFor(Button::Variant variant) {
  switch (variant) {
    case Button::Variant::Default:
      return QStringLiteral("default");
    case Button::Variant::Surface:
      return QStringLiteral("surface");
    case Button::Variant::Ghost:
      return QStringLiteral("ghost");
    case Button::Variant::Subtle:
      return QStringLiteral("subtle");
  }
  return QStringLiteral("default");
}

const Theme& sharedTheme() {
  static Theme instance;
  return instance;
}

buttons::Painter& cachedPainter() {
  static buttons::Painter painter(sharedTheme());
  return painter;
}

}  // namespace

Button::Button(const QString& text, Variant variant, QWidget* parent)
    : QAbstractButton(parent), variant_(variant) {
  setText(text);
  // Python's Button intentionally does NOT setCursor — it inherits the OS
  // arrow. The previous unconditional PointingHandCursor was a port
  // divergence from Python's contract; per-region cursors come from
  // region.cursor and are applied by mouseMoveEvent below.
  setFocusPolicy(Qt::StrongFocus);
  // Python: text buttons start at 32-px min-height (matches Add image 1 /
  // Save current comparison row heights). Icon-only baseline of 36 lives
  // in the Config ctor.
  setMinimumHeight(text.isEmpty() ? 36 : 32);
  setMouseTracking(true);
  controller_ = std::make_unique<buttons::ButtonController>(this);
  controller_->setSpec(buildSimpleSpec(text, variant));
  // Expose the controller through a dynamic property so the shared Painter
  // can discover region geometry without a toolkit-wide base class.
  setProperty("buttonController", QVariant::fromValue(controller_.get()));
  // Keep the _main region's ButtonState::Checked flag in sync with the
  // Qt-level checked flag so paint layers gated on regionStates render the
  // checked variant. Python's Button does this via setChecked(emit=...);
  // C++ funnels both through QAbstractButton's toggled() signal.
  connect(this, &QAbstractButton::toggled, this, [this](bool checked) {
    controller_->setState(QStringLiteral("_main"),
                          buttons::ButtonState::Checked, checked);
    update();
  });
  // Python: `self.theme_manager.theme_changed.connect(self.update)` —
  // repaint on theme switch (light ↔ dark).
  Theme::onThemeChanged(this, [this] { update(); });
}

Button::Button(const Config& config, QWidget* parent)
    : QAbstractButton(parent), variant_(config.variant) {
  setText(config.text);
  // Python's Button intentionally does NOT setCursor — it inherits the OS
  // arrow. The previous unconditional PointingHandCursor was a port
  // divergence from Python's contract; per-region cursors come from
  // region.cursor and are applied by mouseMoveEvent below.
  setFocusPolicy(Qt::StrongFocus);
  setMouseTracking(true);
  controller_ = std::make_unique<buttons::ButtonController>(this);
  setProperty("buttonController", QVariant::fromValue(controller_.get()));
  connect(this, &QAbstractButton::toggled, this, [this](bool checked) {
    controller_->setState(QStringLiteral("_main"),
                          buttons::ButtonState::Checked, checked);
    update();
  });
  // Python: `self.theme_manager.theme_changed.connect(self.update)`.
  Theme::onThemeChanged(this, [this] { update(); });

  buttons::ButtonRegion region;
  region.id = QStringLiteral("_main");
  region.text = config.text;
  if (!config.icon.isNull()) {
    region.icon = QVariant::fromValue(config.icon);
  }
  if (!config.iconChecked.isNull()) {
    region.iconChecked = QVariant::fromValue(config.iconChecked);
  }
  region.variant = variantNameFor(config.variant);
  region.toggle = config.toggle;
  if (config.iconSize.has_value()) {
    region.iconSizePx = config.iconSize;
  }
  region.badge = config.badge;
  if (config.scrollable.has_value()) {
    region.scrollable = config.scrollable;
    scrollMin_ = config.scrollable->first;
    scrollMax_ = config.scrollable->second;
    scrollValue_ = std::max(scrollMin_, 1);
  }
  if (config.longPressMs.has_value()) {
    region.longPress = true;
    region.longPressMs = *config.longPressMs;
  }
  if (config.menu.has_value()) {
    region.menu = config.menu;
  }
  region.showUnderline = config.showUnderline;
  if (config.backgroundColor.has_value()) {
    region.customBgColor = config.backgroundColor;
  }
  if (config.borderColor.has_value()) {
    region.overrideBorderColor = config.borderColor;
  }

  buttons::ButtonSpecArgs args;
  args.variant = variantNameFor(config.variant);
  args.density = config.density;
  args.deferClick = config.deferClick;
  args.wheelRequiresFocus = config.wheelRequiresFocus;
  buttons::ShapeSpec shape;
  if (config.size.has_value()) {
    shape.size = *config.size;
  }
  if (config.iconSize.has_value()) {
    shape.iconSize = *config.iconSize;
  }
  if (config.cornerRadius.has_value()) {
    shape.cornerRadius = *config.cornerRadius;
  }
  args.shape = shape;

  setSpec(buttons::ButtonSpec::fromRegions({region}, args));
  // Mirror Python `Button.__init__` size policy:
  //   - explicit `size=(w, h)` → setFixedSize(w, h)
  //   - text + default (36,36) → setMinimumHeight(32) + Fixed policy
  //   - icon-only default       → setMinimumHeight(36)
  //   - height-only            → setFixedHeight(h)
  //   - width-only             → setFixedWidth(w)
  // Keeps the toolbar text buttons (`Add image 1`, `Save current ...`) at
  // Python's 32-px compact height instead of the chunkier 36 used before.
  if (config.size.has_value()) {
    const int w = config.size->width();
    const int h = config.size->height();
    if (!config.text.isEmpty() && w == 36 && h == 36) {
      // Python: text + default size → minHeight=32, Fixed policy.
      setMinimumHeight(32);
      setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    } else if (w > 0 && h > 0) {
      setFixedSize(w, h);
    } else if (h > 0) {
      setFixedHeight(h);
    } else if (w > 0) {
      setFixedWidth(w);
    }
  } else if (!config.text.isEmpty()) {
    setMinimumHeight(32);
  } else {
    setMinimumHeight(shape.size.height());
  }

  // Auto-attach the capabilities implied by the Config — Python's keyword
  // ctor wires these implicitly and the shell was previously paying the cost
  // of doing it by hand.
  if (config.scrollable.has_value()) {
    addCapability(std::make_unique<buttons::ScrollCapability>(
                      config.scrollable->first, config.scrollable->second),
                  region.id);
  }
  if (config.longPressMs.has_value()) {
    addCapability(
        std::make_unique<buttons::LongPressCapability>(*config.longPressMs),
        region.id);
  }
  if (config.menu.has_value()) {
    addCapability(std::make_unique<buttons::MenuCapability>(*config.menu),
                  region.id);
  }
}

Button::~Button() = default;

void Button::addCapability(
    std::unique_ptr<buttons::ButtonCapability> capability,
    const QString& regionId) {
  if (!capability) {
    return;
  }
  capability->attach(this, regionId);
  if (auto* longPress =
          dynamic_cast<buttons::LongPressCapability*>(capability.get())) {
    connect(longPress, &buttons::LongPressCapability::longPressed, this,
            &Button::longPressed);
  }
  if (auto* menu = dynamic_cast<buttons::MenuCapability*>(capability.get())) {
    connect(menu, &buttons::MenuCapability::menuTriggered, this,
            &Button::menuTriggered);
  }
  if (auto* scroll =
          dynamic_cast<buttons::ScrollCapability*>(capability.get())) {
    scroll->setController(controller_.get());
    connect(scroll, &buttons::ScrollCapability::scrollValueChanged, this,
            [this](const QString&, int) { update(); });
  }
  capabilities_.push_back(std::move(capability));
}

QString Button::variantName(Variant variant) { return variantNameFor(variant); }

buttons::ButtonSpec Button::buildSimpleSpec(const QString& text,
                                             Variant variant) const {
  buttons::ButtonRegion region;
  region.id = QStringLiteral("_main");
  region.text = text;
  region.variant = variantNameFor(variant);

  buttons::ButtonSpecArgs args;
  args.variant = variantNameFor(variant);
  args.shape = buttons::ShapeSpec{};
  return buttons::ButtonSpec::fromRegions({region}, args);
}

QSize Button::sizeHint() const {
  // 1:1 with Python `_ButtonStyleApi.sizeHint`:
  //   if has_text:
  //       w = textW + iconW + 24
  //       h = max(32, fontHeight + 16)
  //   else:
  //       w = h = 36   (icon-only baseline)
  // The previous C++ implementation hard-coded a `max(44, …)` width floor
  // and used `shape.height = 36`, producing a chunkier hint that paints a
  // wider/taller button than Python does — caught by the parity tester.
  const auto& regions = controller_->regions();
  const bool hasText = !text().isEmpty() ||
                      (!regions.empty() && !regions.front().text.isEmpty());
  if (!hasText) {
    return QSize(36, 36);
  }
  const QFontMetrics fm = fontMetrics();
  const int textW = fm.horizontalAdvance(text());
  bool hasIcon = false;
  int iconSizePx = controller_->spec().shape.iconSize;
  if (!regions.empty()) {
    const auto& r0 = regions.front();
    if (r0.icon.isValid() && r0.icon.canConvert<QIcon>() &&
        !r0.icon.value<QIcon>().isNull()) {
      hasIcon = true;
    }
    if (r0.iconSizePx.has_value()) {
      iconSizePx = *r0.iconSizePx;
    }
  }
  const int iconW = hasIcon ? iconSizePx + 6 : 0;
  const int w = textW + iconW + 24;
  const int h = std::max(32, fm.height() + 16);
  return QSize(w, h);
}

void Button::setVariant(Variant variant) {
  if (variant_ == variant) {
    return;
  }
  variant_ = variant;
  controller_->setSpec(buildSimpleSpec(text(), variant));
  update();
}

void Button::setSpec(buttons::ButtonSpec spec) {
  controller_->setSpec(std::move(spec));
  // Mirror Python: any region declaring toggle behavior makes the widget
  // checkable at the Qt level so isChecked() flows into ButtonState::Checked.
  bool checkable = false;
  for (const auto& region : controller_->regions()) {
    if (region.toggle) {
      checkable = true;
      break;
    }
  }
  setCheckable(checkable);
  hasToggle_ = checkable;
  update();
}

// Python's `setChecked` gates on `_has_toggle` — won't change state or emit
// if toggle support isn't declared.  QAbstractButton::setChecked always fires
// toggled(); we override to match the Python contract.
void Button::setChecked(bool checked) {
  if (!hasToggle_) {
    return;
  }
  if (isChecked() != checked) {
    QAbstractButton::setChecked(checked);
  }
}

const buttons::ButtonSpec& Button::spec() const { return controller_->spec(); }

void Button::setIconSizePx(int sizePx) {
  sizePx = std::max(1, sizePx);
  // Mutate the _main region's iconSizePx in the live spec and push the
  // updated spec back so the next paint picks up the new value.
  buttons::ButtonSpec updated = controller_->spec();
  for (auto& region : updated.regions) {
    if (region.id == QStringLiteral("_main")) {
      region.style.iconSizePx = sizePx;
    }
  }
  controller_->setSpec(std::move(updated));
  updateGeometry();
  update();
}

void Button::setRippleColors(QColor colorFrom, QColor colorTo) {
  rippleColorFrom_ = std::move(colorFrom);
  rippleColorTo_ = std::move(colorTo);
}

void Button::clearRippleColors() {
  rippleColorFrom_.reset();
  rippleColorTo_.reset();
}

void Button::setValue(int val) {
  val = std::max(scrollMin_, std::min(scrollMax_, val));
  if (scrollValue_ != val) {
    scrollValue_ = val;
    emit valueChanged(val);
    update();
  }
}

void Button::setRange(int minV, int maxV) {
  scrollMin_ = minV;
  scrollMax_ = maxV;
  scrollValue_ = std::max(minV, std::min(maxV, scrollValue_));
}

void Button::paintEvent(QPaintEvent*) {
  QPainter qp(this);
  buttons::DrawContext ctx;
  ctx.widget = this;
  ctx.painter = &qp;
  ctx.rect = QRectF(rect());
  // Python: corner_radius = 2 if has_text else 6 (default values).
  // Shape spec's cornerRadius overrides these defaults.
  const bool hasText = !text().isEmpty();
  ctx.cornerRadius = 6;  // icon-only default
  if (hasText) {
    ctx.cornerRadius = 2;
  }
  if (controller_->spec().shape.cornerRadius.has_value()) {
    ctx.cornerRadius = *controller_->spec().shape.cornerRadius;
  }
  ctx.variant = buttons::getVariant(variantNameFor(variant_));
  // Authoritative state source is the controller's _main runtime — Qt-level
  // checked/disabled are mirrored there by setSpec/toggled connects, and
  // hover/press get there via the mouse handlers (or directly when tests
  // force a state). Reading from the controller means a state set «out of
  // band» (parity test, programmatic toggle) still drives paint.
  ctx.states = controller_->states(QStringLiteral("_main"));
  if (!isEnabled()) {
    ctx.states.setFlag(buttons::ButtonState::Disabled, true);
  }
  if (isChecked()) {
    ctx.states.setFlag(buttons::ButtonState::Checked, true);
  }
  if (underMouse()) {
    ctx.states.setFlag(buttons::ButtonState::Hovered, true);
  }
  if (isDown()) {
    ctx.states.setFlag(buttons::ButtonState::Pressed, true);
  }
  if (hasFocus()) {
    ctx.states.setFlag(buttons::ButtonState::Focused, true);
  }
  // Mirror Python `_build_content`: derive widget-scope content from the
  // first region's spec (rows / icon+text / text / icon). Fall back to the
  // widget's text() so a bare Button("foo") keeps working when no spec is
  // attached.
  const auto& regions = controller_->regions();
  std::shared_ptr<buttons::Content> derived;
  if (!regions.empty()) {
    derived = buttons::buildContentFromRegion(regions.front());
  }
  if (!derived) {
    derived = std::make_shared<buttons::TextContent>(text());
  }
  ctx.content = derived;

  // Single-region (widget-scope) paint needs the region's style pulled
  // into the ctx — otherwise BackgroundLayer / UnderlineLayer have no way
  // to see `customBgColor`, `overrideBgColor`, `showUnderline`,
  // `underlineColor`, etc. The multi-region path uses scopedTo() which
  // already does this; the single-region fast path used to skip the copy
  // entirely, so `cfg.backgroundColor` (Python's `background_color=`) was
  // silently dropped.
  if (!regions.empty()) {
    const auto& r0 = regions.front();
    ctx.customBgColor = r0.customBgColor;
    ctx.overrideBgColor = r0.overrideBgColor;
    ctx.overrideBorderColor = r0.overrideBorderColor;
    if (r0.showUnderline.has_value()) {
      ctx.showUnderline = *r0.showUnderline;
    }
    if (r0.underlineColor.isValid()) {
      ctx.underlineColor = r0.underlineColor;
    }
    if (r0.underlineThickness.has_value()) {
      ctx.underlineThickness = r0.underlineThickness;
    }
    if (r0.iconSizePx.has_value()) {
      ctx.iconSizePx = *r0.iconSizePx;
    }
    if (r0.variant.has_value()) {
      ctx.variant = buttons::getVariant(*r0.variant);
    }
    ctx.showStrikeThrough = r0.showStrikeThrough;
  }

  cachedPainter().paint(ctx);
}

void Button::resizeEvent(QResizeEvent* event) {
  QAbstractButton::resizeEvent(event);
  controller_->recomputeRects();
}

void Button::mousePressEvent(QMouseEvent* event) {
  QAbstractButton::mousePressEvent(event);
  const auto regionId = controller_->regionAt(event->position());
  pressedRegion_ = regionId;

  // Emit button-level and region-level pressed signals.
  emit pressed();
  if (regionId.has_value()) {
    emit regionPressed(*regionId);
  }
  if (event->button() == Qt::RightButton) {
    emit rightClicked();
  }
  if (event->button() == Qt::MiddleButton) {
    emit middleClicked();
  }
  if (regionId.has_value()) {
    controller_->setState(regionId, buttons::ButtonState::Pressed, true);
    if (isEnabled()) {
      // Fire the region's ripple at the click point. Python: `ripple =
      // self.region_ripple(region_id) or self._ripple;
      // ripple.trigger(pos, color_from, color_to)`. If no explicit override
      // colors are configured, pass nullopt so RippleLayer paints the
      // default overlay (white on dark / black on light).
      if (auto* ripple = controller_->ripple(*regionId); ripple != nullptr) {
        ripple->trigger(event->position(), rippleColorFrom_, rippleColorTo_);
      }
    }
  }
  // Long-press capabilities arm on press; click in mouseReleaseEvent is
  // suppressed when they fire first.
  for (const auto& cap : capabilities_) {
    if (auto* longPress =
            dynamic_cast<buttons::LongPressCapability*>(cap.get())) {
      longPress->onPressStart();
    }
  }
  update();
}

void Button::mouseReleaseEvent(QMouseEvent* event) {
  const auto pressed = pressedRegion_;
  if (pressed.has_value()) {
    controller_->setState(pressed, buttons::ButtonState::Pressed, false);
    emit regionReleased(*pressed);
  }
  emit released();
  pressedRegion_.reset();

  bool longPressTriggered = false;
  for (const auto& cap : capabilities_) {
    if (auto* longPress =
            dynamic_cast<buttons::LongPressCapability*>(cap.get())) {
      if (longPress->wasLongPressed()) {
        longPressTriggered = true;
      }
      longPress->onPressEnd();
    }
  }

  if (!longPressTriggered && pressed.has_value() &&
      controller_->regionAt(event->position()) == pressed) {
    // Toggle+scroll combined click — Python's `_do_toggle_scroll_click`.
    // When a button is both toggleable and scrollable, clicking toggles
    // and saves/restores the scroll value.
    const bool hasToggle = isCheckable();
    const bool hasScroll =
        scrollMin_ != scrollMax_ || scrollValue_ != 0;
    if (hasToggle && hasScroll) {
      if (!isChecked()) {
        if (scrollValue_ > 0) {
          savedScrollValue_ = scrollValue_;
        }
        scrollValue_ = 0;
        setChecked(true);
        if (!signalsBlocked()) {
          emit valueChanged(0);
        }
      } else {
        const int restored =
            (savedScrollValue_.has_value() && *savedScrollValue_ > 0)
                ? *savedScrollValue_
                : 1;
        savedScrollValue_.reset();
        scrollValue_ = restored;
        setChecked(false);
        if (!signalsBlocked()) {
          emit valueChanged(restored);
        }
      }
      update();
      QAbstractButton::mouseReleaseEvent(event);
      return;
    }
    // Menu capability swallows the click when bound to this region.
    bool menuShown = false;
    for (const auto& cap : capabilities_) {
      if (auto* menu = dynamic_cast<buttons::MenuCapability*>(cap.get())) {
        if (cap->regionId() == *pressed || cap->regionId().isEmpty()) {
          menu->showMenu();
          menuShown = true;
          break;
        }
      }
    }
    if (!menuShown) {
      emit regionClicked(*pressed);
    }
  }
  update();
  QAbstractButton::mouseReleaseEvent(event);
}

void Button::wheelEvent(QWheelEvent* event) {
  for (const auto& cap : capabilities_) {
    if (auto* scroll = dynamic_cast<buttons::ScrollCapability*>(cap.get())) {
      if (scroll->handleWheelEvent(event)) {
        return;
      }
    }
  }
  QAbstractButton::wheelEvent(event);
}

void Button::mouseMoveEvent(QMouseEvent* event) {
  const auto regionId = controller_->regionAt(event->position());
  if (regionId != hoveredRegion_) {
    if (hoveredRegion_.has_value()) {
      controller_->setState(hoveredRegion_, buttons::ButtonState::Hovered,
                            false);
    }
    hoveredRegion_ = regionId;
    if (regionId.has_value()) {
      controller_->setState(regionId, buttons::ButtonState::Hovered, true);
    }
    // Apply the hovered region's custom cursor (if any), or restore the
    // widget default — mirrors the dataclass field `ButtonRegion.cursor`.
    // Without a region cursor we unset, so Button never imposes a cursor
    // (matches Python which never calls setCursor on the widget).
    if (regionId.has_value()) {
      for (const auto& r : controller_->regions()) {
        if (r.id == *regionId) {
          if (r.cursor.has_value()) {
            setCursor(*r.cursor);
          } else {
            unsetCursor();
          }
          break;
        }
      }
    } else {
      unsetCursor();
    }
    update();
  }
  QAbstractButton::mouseMoveEvent(event);
}

void Button::enterEvent(QEnterEvent* event) {
  QAbstractButton::enterEvent(event);
  update();
}

void Button::keyPressEvent(QKeyEvent* event) {
  // Python's Button fires on Space (Qt default) AND Return/Enter. Forward
  // Return/Enter through animateClick so QAbstractButton emits clicked()
  // and toggled() exactly as the Python contract specifies.
  if (event->key() == Qt::Key_Return || event->key() == Qt::Key_Enter) {
    // Synchronous click — animateClick schedules a 100ms timer that breaks
    // single-shot QSignalSpy verification under QTest. click() fires the
    // press/release pair immediately, which is what Python's Button does
    // via QAbstractButton's keyboard handling.
    click();
    event->accept();
    return;
  }
  QAbstractButton::keyPressEvent(event);
}

void Button::leaveEvent(QEvent* event) {
  if (hoveredRegion_.has_value()) {
    controller_->setState(hoveredRegion_, buttons::ButtonState::Hovered, false);
    hoveredRegion_.reset();
  }
  if (pressedRegion_.has_value()) {
    controller_->setState(pressedRegion_, buttons::ButtonState::Pressed, false);
    pressedRegion_.reset();
  }
  update();
  QAbstractButton::leaveEvent(event);
}

}  // namespace sli::toolkit
