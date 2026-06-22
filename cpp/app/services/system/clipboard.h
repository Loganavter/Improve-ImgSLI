#pragma once

#include <QStringList>

namespace imgsli::app::services::system {

// Inspect the system clipboard for image-like content. Returns a list of
// resolvable inputs in priority order:
//   1. Local file paths and `file://` URLs found in clipboard text.
//   2. `http(s)://` URLs found in clipboard text.
//   3. URLs from `QMimeData::urls()` (local + remote).
//   4. If nothing above is found and the clipboard carries a raw QImage,
//      it is saved to a temporary PNG and that path is returned.
//
// The returned strings are either filesystem paths (absolute) or `http(s)://`
// URLs — the caller is expected to discriminate.
QStringList collectClipboardImageItems();

}  // namespace imgsli::app::services::system
