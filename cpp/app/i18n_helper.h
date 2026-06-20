// Thin C++ shim over imgsli_core::i18n. Centralizes the cxx call so widgets
// can write `imgsli::app::tr("settings.appearance")` without pulling in the
// bridge header at every callsite.

#pragma once

#include <QString>

#include "imgsli_core_bridge/bridge.h"

namespace imgsli::app {

inline void initI18n(const QString& root) {
  const QByteArray utf8 = root.toUtf8();
  imgsli::i18n_init(
      std::string(utf8.constData(), static_cast<std::size_t>(utf8.size())));
}

inline void setLanguage(const QString& lang) {
  const QByteArray utf8 = lang.toUtf8();
  imgsli::i18n_set_language(
      std::string(utf8.constData(), static_cast<std::size_t>(utf8.size())));
}

inline QString tr(const QString& key) {
  const QByteArray utf8 = key.toUtf8();
  const rust::String out = imgsli::i18n_translate(
      std::string(utf8.constData(), static_cast<std::size_t>(utf8.size())));
  return QString::fromUtf8(out.data(), static_cast<int>(out.size()));
}

}  // namespace imgsli::app
