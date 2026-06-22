#pragma once

#include <QColor>
#include <QLabel>
#include <QString>

#include <optional>

namespace sli::toolkit {

// ============================================================================
// VARIANT SYSTEM: LabelVariantSpec defines shared label presets
// ============================================================================

struct LabelVariantSpec {
  QString name;
  std::optional<int> pixel_size;
  bool bold = false;
  QString color_token{"dialog.text"};
  int minimum_width = 0;
  bool expanding = false;
  bool elide = false;
};

// Preset registry for label variants
void registerLabelVariant(const LabelVariantSpec& spec);
LabelVariantSpec getLabelVariant(const QString& name);

// ============================================================================
// LABEL CONFIG: Configure a Label with dataclass-like structure
// ============================================================================

struct LabelConfig {
  QString text;
  QString variant{"body"};
  std::optional<QString> family;
  std::optional<int> pixel_size;
  std::optional<bool> bold;
  std::optional<bool> italic;
  std::optional<bool> underline;
  std::optional<bool> strike_out;
  std::optional<QColor> color;
  std::optional<QString> color_token;
  Qt::Alignment alignment{Qt::AlignVCenter | Qt::AlignLeft};
  std::optional<bool> elide;
  std::optional<int> minimum_width;
  std::optional<bool> expanding;
  std::optional<bool> word_wrap;
  bool selectable = false;
};

// ============================================================================
// LABEL: Unified themed text label with variant system
// ============================================================================

class Label final : public QLabel {
  Q_OBJECT

 public:
  // Main constructor: text + optional parent + optional keyword arguments
  explicit Label(const QString& text = {}, QWidget* parent = nullptr);

  // Constructor with variant override
  explicit Label(const QString& text, const QString& variant,
                 QWidget* parent = nullptr);

  // Constructor from LabelConfig
  explicit Label(const LabelConfig& config, QWidget* parent = nullptr);

  // ========================================================================
  // VARIANT SYSTEM - change preset
  // ========================================================================
  QString variant() const { return variant_name_; }
  void setVariant(const QString& variant);

  // ========================================================================
  // STYLING OVERRIDES - individual font/color tweaks
  // ========================================================================
  void setTextColor(const std::optional<QColor>& color);
  void setColorToken(const std::optional<QString>& token);
  void setPixelSize(const std::optional<int>& size);
  void setFamily(const std::optional<QString>& family);
  void setBold(const std::optional<bool>& enabled);
  void setItalic(const std::optional<bool>& enabled);
  void setUnderline(const std::optional<bool>& enabled);
  void setStrikeOut(const std::optional<bool>& enabled);
  void setSelectable(bool enabled);

  // ========================================================================
  // SIZE / ELIDE POLICY
  // ========================================================================
  void setMinimumWidth(int width);
  void setText(const QString& text);

  // ========================================================================
  // ACCESSORS & UTILITIES
  // ========================================================================
  QString getOriginalText() const { return original_text_; }
  void invalidateSizeCache();

 protected:
  void resizeEvent(QResizeEvent* event) override;
  void changeEvent(QEvent* event) override;

 private:
  // ========================================================================
  // INTERNAL STYLING ENGINE
  // ========================================================================
  void applyStyle();
  void updateElidedText();

  // ========================================================================
  // INTERNAL HELPERS - query variant/override state
  // ========================================================================
  std::optional<QColor> resolveColor(const LabelVariantSpec& spec);
  int minimumWidth() const;
  bool expanding() const;
  bool usesElide() const;

  // ========================================================================
  // SIZE HINTS
  // ========================================================================
  QSize sizeHint() const override;
  QSize minimumSizeHint() const override;

  // ========================================================================
  // STATE: variant name + all styling overrides
  // ========================================================================
  QString variant_name_{"body"};

  // Font overrides
  std::optional<QString> family_override_;
  std::optional<int> pixel_size_override_;
  std::optional<bool> bold_override_;
  std::optional<bool> italic_override_;
  std::optional<bool> underline_override_;
  std::optional<bool> strike_out_override_;

  // Color overrides
  std::optional<QColor> color_override_;
  std::optional<QString> color_token_override_;

  // Elide & layout overrides
  std::optional<bool> elide_override_;
  std::optional<int> minimum_width_override_;
  std::optional<bool> expanding_override_;
  std::optional<bool> word_wrap_override_;

  // Text state
  QString original_text_;
  mutable std::optional<int> preferred_width_cache_;
};

}  // namespace sli::toolkit
