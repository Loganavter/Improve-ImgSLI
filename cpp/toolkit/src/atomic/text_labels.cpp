#include "sli/toolkit/atomic/text_labels.h"

#include <QEvent>
#include <QFont>
#include <QFontMetrics>
#include <QSizePolicy>
#include <Qt>

#include "sli/toolkit/theme.h"

#include <unordered_map>

namespace sli::toolkit {

// ============================================================================
// VARIANT SYSTEM: Global registry of label presets
// ============================================================================

namespace {

// Global variant registry
std::unordered_map<std::string, LabelVariantSpec>& variantRegistry() {
  static std::unordered_map<std::string, LabelVariantSpec> registry;
  return registry;
}

// Initialize default variants on first use
void ensureDefaultVariants() {
  auto& reg = variantRegistry();
  if (!reg.empty()) return;

  // body: default text size (12px, not bold)
  reg["body"] = LabelVariantSpec{
      QString("body"),
      12,  // pixel_size
      false,
      "dialog.text",
      0,  // minimum_width
      false,
      false,  // elide
  };

  // caption: small text (11px, not bold)
  reg["caption"] = LabelVariantSpec{
      QString("caption"),
      11,  // pixel_size
      false,
      "dialog.text",
      0,  // minimum_width
      false,
      false,  // elide
  };

  // compact: small + adaptive width (10px, expanding, elided)
  reg["compact"] = LabelVariantSpec{
      QString("compact"),
      10,  // pixel_size
      false,
      "dialog.text",
      80,  // minimum_width
      true,  // expanding
      true,  // elide
  };

  // group-title: section header (13px, bold, elided)
  reg["group-title"] = LabelVariantSpec{
      QString("group-title"),
      13,  // pixel_size
      true,  // bold
      "dialog.text",
      0,  // minimum_width
      false,  // expanding
      true,  // elide
  };

  // adaptive: general-purpose adaptive (12px, expanding, elided, min-width 50)
  reg["adaptive"] = LabelVariantSpec{
      QString("adaptive"),
      12,  // pixel_size
      false,
      "dialog.text",
      50,  // minimum_width
      true,  // expanding
      true,  // elide
  };
}

}  // namespace

void registerLabelVariant(const LabelVariantSpec& spec) {
  ensureDefaultVariants();
  variantRegistry()[spec.name.toLower().toStdString()] = spec;
}

LabelVariantSpec getLabelVariant(const QString& name) {
  ensureDefaultVariants();
  auto& reg = variantRegistry();
  QString keyName = (name.isEmpty() ? "body" : name).toLower();
  auto it = reg.find(keyName.toStdString());
  if (it != reg.end()) {
    return it->second;
  }
  // Fallback to "body"
  return reg.at("body");
}

// ============================================================================
// CONSTRUCTORS
// ============================================================================

Label::Label(const QString& text, QWidget* parent)
    : Label(text, "body", parent) {}

Label::Label(const QString& text, const QString& variant, QWidget* parent)
    : QLabel(text, parent),
      variant_name_(variant.isEmpty() ? "body" : variant),
      original_text_(text) {
  ensureDefaultVariants();

  // Set default alignment
  setAlignment(Qt::AlignVCenter | Qt::AlignLeft);

  // Apply initial style
  applyStyle();
}

Label::Label(const LabelConfig& config, QWidget* parent)
    : QLabel(parent),
      variant_name_(config.variant),
      family_override_(config.family),
      pixel_size_override_(config.pixel_size),
      bold_override_(config.bold),
      italic_override_(config.italic),
      underline_override_(config.underline),
      strike_out_override_(config.strike_out),
      color_override_(config.color),
      color_token_override_(config.color_token),
      elide_override_(config.elide),
      minimum_width_override_(config.minimum_width),
      expanding_override_(config.expanding),
      word_wrap_override_(config.word_wrap),
      original_text_(config.text) {
  ensureDefaultVariants();

  setAlignment(config.alignment);
  setWordWrap(config.word_wrap.value_or(false));

  if (config.selectable) {
    setTextInteractionFlags(Qt::TextSelectableByMouse |
                           Qt::TextSelectableByKeyboard);
  }

  QLabel::setText(config.text);
  applyStyle();
}

// ============================================================================
// VARIANT SYSTEM - Change preset
// ============================================================================

void Label::setVariant(const QString& variant) {
  QString newVariant = variant.isEmpty() ? "body" : variant;
  if (newVariant == variant_name_) {
    return;
  }
  variant_name_ = newVariant;
  preferred_width_cache_.reset();
  applyStyle();
}

// ============================================================================
// STYLING OVERRIDES
// ============================================================================

void Label::setTextColor(const std::optional<QColor>& color) {
  color_override_ = color;
  applyStyle();
}

void Label::setColorToken(const std::optional<QString>& token) {
  color_token_override_ = token;
  applyStyle();
}

void Label::setPixelSize(const std::optional<int>& size) {
  if (size.has_value()) {
    pixel_size_override_ = std::max(1, size.value());
  } else {
    pixel_size_override_.reset();
  }
  preferred_width_cache_.reset();
  applyStyle();
}

void Label::setFamily(const std::optional<QString>& family) {
  family_override_ = family;
  preferred_width_cache_.reset();
  applyStyle();
}

void Label::setBold(const std::optional<bool>& enabled) {
  bold_override_ = enabled;
  preferred_width_cache_.reset();
  applyStyle();
}

void Label::setItalic(const std::optional<bool>& enabled) {
  italic_override_ = enabled;
  preferred_width_cache_.reset();
  applyStyle();
}

void Label::setUnderline(const std::optional<bool>& enabled) {
  underline_override_ = enabled;
  preferred_width_cache_.reset();
  applyStyle();
}

void Label::setStrikeOut(const std::optional<bool>& enabled) {
  strike_out_override_ = enabled;
  preferred_width_cache_.reset();
  applyStyle();
}

void Label::setSelectable(bool enabled) {
  if (enabled) {
    setTextInteractionFlags(Qt::TextSelectableByMouse |
                           Qt::TextSelectableByKeyboard);
  } else {
    setTextInteractionFlags(Qt::NoTextInteraction);
  }
}

// ============================================================================
// SIZE / ELIDE POLICY
// ============================================================================

void Label::setMinimumWidth(int width) {
  minimum_width_override_ = std::max(0, width);
  QLabel::setMinimumWidth(width);
  preferred_width_cache_.reset();
  updateGeometry();
}

void Label::setText(const QString& text) {
  original_text_ = text;
  preferred_width_cache_.reset();
  QLabel::setText(text);
  updateElidedText();
  updateGeometry();
}

// ============================================================================
// UTILITIES
// ============================================================================

void Label::invalidateSizeCache() {
  preferred_width_cache_.reset();
  updateGeometry();
}

// ============================================================================
// EVENT HANDLERS
// ============================================================================

void Label::resizeEvent(QResizeEvent* event) {
  QLabel::resizeEvent(event);
  updateElidedText();
}

void Label::changeEvent(QEvent* event) {
  QLabel::changeEvent(event);
  if (event->type() == QEvent::ApplicationFontChange) {
    preferred_width_cache_.reset();
    applyStyle();
  }
}

// ============================================================================
// SIZE HINTS
// ============================================================================

QSize Label::sizeHint() const {
  QSize hint = QLabel::sizeHint();
  if (usesElide()) {
    int minWidth = minimumWidth();
    if (!preferred_width_cache_.has_value()) {
      QFontMetrics fm(font());
      preferred_width_cache_ =
          fm.horizontalAdvance(original_text_) + 10;
    }
    hint.setWidth(std::max(preferred_width_cache_.value(), minWidth));
  }
  return hint;
}

QSize Label::minimumSizeHint() const {
  QSize hint = QLabel::minimumSizeHint();
  int minWidth = minimumWidth();
  if (minWidth > 0) {
    hint.setWidth(minWidth);
  }
  return hint;
}

// ============================================================================
// INTERNAL STYLING ENGINE
// ============================================================================

void Label::applyStyle() {
  // Get variant spec
  LabelVariantSpec spec = getLabelVariant(variant_name_);

  // Apply font
  QFont font = this->font();

  // Set pixel size from override or spec
  int pixelSize = pixel_size_override_.value_or(spec.pixel_size.value_or(12));
  pixelSize = std::max(1, pixelSize);
  font.setPixelSize(pixelSize);

  // Apply font family if overridden
  if (family_override_.has_value()) {
    font.setFamily(family_override_.value());
  }

  // Apply bold: override takes precedence, then spec
  bool bold = bold_override_.value_or(spec.bold);
  font.setBold(bold);

  // Apply italic
  font.setItalic(italic_override_.value_or(false));

  // Apply underline
  font.setUnderline(underline_override_.value_or(false));

  // Apply strikeout
  font.setStrikeOut(strike_out_override_.value_or(false));

  setFont(font);

  // Resolve and apply color
  std::optional<QColor> resolvedColor = resolveColor(spec);
  if (resolvedColor.has_value()) {
    // Use QColor::name(HexArgb) to get hex color string
    QString colorStr = resolvedColor.value().name(QColor::HexArgb);
    setStyleSheet(QString("color: %1;").arg(colorStr));
  } else {
    // Clear any previously set stylesheet
    setStyleSheet("");
  }

  // Apply size policy (expanding vs preferred)
  if (expanding()) {
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
  } else {
    setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Fixed);
  }

  // Apply minimum width
  int minWidth = minimumWidth();
  if (minWidth > 0) {
    QLabel::setMinimumWidth(minWidth);
  }

  // Update text (may be elided)
  updateElidedText();
  updateGeometry();
  update();
}

void Label::updateElidedText() {
  if (!usesElide() || original_text_.isEmpty()) {
    // No elide: just use original text
    if (text() != original_text_) {
      QLabel::setText(original_text_);
    }
    return;
  }

  int availableWidth = width() - 10;
  if (availableWidth <= 0) {
    return;
  }

  QFontMetrics fm(font());
  if (fm.horizontalAdvance(original_text_) <= availableWidth) {
    // Text fits: no elision needed
    if (text() != original_text_) {
      QLabel::setText(original_text_);
    }
  } else {
    // Text is too wide: apply elision
    QString elidedText =
        fm.elidedText(original_text_, Qt::ElideRight, availableWidth);
    if (text() != elidedText) {
      QLabel::setText(elidedText);
    }
  }
}

// ============================================================================
// INTERNAL HELPERS - Query variant/override state
// ============================================================================

std::optional<QColor> Label::resolveColor(const LabelVariantSpec& spec) {
  // Priority 1: explicit color override
  if (color_override_.has_value()) {
    return color_override_;
  }

  // Priority 2: color token override or variant spec token
  QString token = color_token_override_.value_or(spec.color_token);
  auto color = Theme::tryGetColor(token);
  if (color.has_value()) {
    return color;
  }

  // Fallback: try WindowText token
  auto fallback = Theme::tryGetColor("WindowText");
  return fallback;
}

int Label::minimumWidth() const {
  if (minimum_width_override_.has_value()) {
    return std::max(0, minimum_width_override_.value());
  }
  return std::max(0, getLabelVariant(variant_name_).minimum_width);
}

bool Label::expanding() const {
  if (expanding_override_.has_value()) {
    return expanding_override_.value();
  }
  return getLabelVariant(variant_name_).expanding;
}

bool Label::usesElide() const {
  if (elide_override_.has_value()) {
    return elide_override_.value();
  }
  return getLabelVariant(variant_name_).elide;
}

}  // namespace sli::toolkit
