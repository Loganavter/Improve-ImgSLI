#include "store.h"

#include <QByteArray>
#include <QMetaObject>

#include <string>

namespace {

QString rsToQString(const rust::String& value) {
    return QString::fromUtf8(value.data(), static_cast<qsizetype>(value.size()));
}

}  // namespace

namespace imgsli::app {

Store::Store(QObject* parent)
    : QObject(parent),
      rustStore_(imgsli::new_store()) {}

QString Store::stateJson() const {
    return rsToQString(imgsli::store_state_json(*rustStore_));
}

bool Store::dispatch(const QString& actionJson) {
    const QByteArray utf8 = actionJson.toUtf8();
    try {
        const auto result = imgsli::store_dispatch(
            *rustStore_,
            *this,
            std::string(utf8.constData(), static_cast<std::size_t>(utf8.size())));
        Q_UNUSED(result);
        return true;
    } catch (const std::exception& ex) {
        emit dispatchFailed(QString::fromUtf8(ex.what()));
        return false;
    }
}

void Store::on_rust_state_changed(
    rust::String stateJson,
    rust::String scope) {
    const QString state = rsToQString(stateJson);
    const QString changedScope = rsToQString(scope);
    QMetaObject::invokeMethod(
        this,
        [this, state, changedScope]() {
            emit stateChanged(state, changedScope);
        },
        Qt::QueuedConnection);
}

}  // namespace imgsli::app
