#pragma once

#include <QHash>
#include <QJsonObject>
#include <QString>
#include <QUuid>

#include <optional>
#include <utility>
#include <vector>

namespace imgsli::app::domain {

struct WorkspaceSession {
  QString id;
  QString title;
  QString sessionType;
  QJsonObject document;
  QJsonObject viewport;
  QHash<QString, QJsonObject> stateSlots;
  QHash<QString, QJsonObject> resources;
  QHash<QString, QJsonObject> metadata;
};

class WorkspaceState {
 public:
  const std::vector<WorkspaceSession>& sessions() const { return sessions_; }
  std::vector<WorkspaceSession>& sessionsMut() { return sessions_; }
  const std::optional<QString>& activeSessionId() const {
    return activeSessionId_;
  }
  void setActiveSessionId(std::optional<QString> id) {
    activeSessionId_ = std::move(id);
  }

  QString nextDefaultTitle(const QString& sessionType) {
    const int next = titleCounters_.value(sessionType, 0) + 1;
    titleCounters_.insert(sessionType, next);
    QString suffix = sessionType;
    suffix.replace(QLatin1Char('_'), QLatin1Char(' '));
    // Title-case first letter of each word.
    bool capitalizeNext = true;
    for (auto& ch : suffix) {
      if (capitalizeNext && ch.isLetter()) {
        ch = ch.toUpper();
        capitalizeNext = false;
      } else if (ch == QLatin1Char(' ')) {
        capitalizeNext = true;
      }
    }
    return QStringLiteral("%1 %2").arg(suffix).arg(next);
  }

  static QString newSessionId() {
    return QUuid::createUuid().toString(QUuid::WithoutBraces);
  }

 private:
  std::vector<WorkspaceSession> sessions_;
  std::optional<QString> activeSessionId_;
  QHash<QString, int> titleCounters_;
};

}  // namespace imgsli::app::domain
