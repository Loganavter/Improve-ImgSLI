#pragma once

#include <QWidget>

class QLabel;

namespace sli::toolkit {

/// Compact product-style section heading with optional supporting text.
class SectionHeader final : public QWidget {
  Q_OBJECT

 public:
  explicit SectionHeader(const QString& title = {},
                         const QString& description = {},
                         QWidget* parent = nullptr);

  QString title() const;
  void setTitle(const QString& title);
  QString description() const;
  void setDescription(const QString& description);

 private:
  QLabel* titleLabel_ = nullptr;
  QLabel* descriptionLabel_ = nullptr;
};

}  // namespace sli::toolkit
