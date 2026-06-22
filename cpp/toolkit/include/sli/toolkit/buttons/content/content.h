#pragma once

#include <QIcon>
#include <QString>
#include <QVariant>

#include <memory>
#include <optional>
#include <vector>

#include "sli/toolkit/buttons/content/button_row.h"

namespace sli::toolkit {
class Theme;
}

namespace sli::toolkit::buttons {

struct DrawContext;
struct ButtonRegion;

class Content {
 public:
  virtual ~Content() = default;
  virtual void draw(const DrawContext& ctx, const Theme& theme) const = 0;
};

class TextContent final : public Content {
 public:
  explicit TextContent(QString text) : text_(std::move(text)) {}
  void draw(const DrawContext& ctx, const Theme& theme) const override;
  const QString& text() const { return text_; }

 private:
  QString text_;
};

class RowsContent final : public Content {
 public:
  RowsContent(std::vector<ButtonRow> rows, bool compact = false, int rowGap = 2)
      : rows_(std::move(rows)), compact_(compact), rowGap_(rowGap) {}
  void draw(const DrawContext& ctx, const Theme& theme) const override;
  const std::vector<ButtonRow>& rows() const { return rows_; }
  bool compact() const { return compact_; }
  int rowGap() const { return rowGap_; }

 private:
  std::vector<ButtonRow> rows_;
  bool compact_;
  int rowGap_;
};

class IconContent final : public Content {
 public:
  IconContent() = default;
  IconContent(QIcon unchecked, QIcon checked)
      : iconUnchecked_(std::move(unchecked)), iconChecked_(std::move(checked)) {}
  void draw(const DrawContext& ctx, const Theme& theme) const override;
  const QIcon& iconUnchecked() const { return iconUnchecked_; }
  const QIcon& iconChecked() const { return iconChecked_; }

 private:
  static void drawStandard(QPainter* p, const QRect& rect, const QIcon& icon,
                           std::optional<int> scrollValue, bool alwaysVisible,
                           bool isToggleScroll, int iconSize);
  static void drawWithHoverValue(QPainter* p, const QRect& rect,
                                  const QIcon& icon, int scrollValue,
                                  int iconSize);
  static void drawScrollValueBelow(QPainter* p, const QRect& rect, int value);
  static void drawValueText(QPainter* p, const QRect& rect, int y, int height,
                            const QString& text);

  QIcon iconUnchecked_;
  QIcon iconChecked_;
};

class IconTextContent final : public Content {
 public:
  IconTextContent(QIcon icon, QString text)
      : icon_(std::move(icon)), text_(std::move(text)) {}
  void draw(const DrawContext& ctx, const Theme& theme) const override;
  const QIcon& icon() const { return icon_; }
  const QString& text() const { return text_; }

 private:
  QIcon icon_;
  QString text_;
};

// Build a Content object from a region's icon/text/rows fields. Mirrors
// Python's `_build_content` / `_build_region_content`: rows → RowsContent,
// icon+text → IconTextContent, text → TextContent, icon → IconContent.
// Returns nullptr if the region carries none of the three.
std::shared_ptr<Content> buildContentFromRegion(const ButtonRegion& region);

}  // namespace sli::toolkit::buttons
