#pragma once

#include <QObject>
#include <QString>

#include "imgsli_core_bridge/bridge.h"

namespace imgsli::app {

class Store final : public QObject, public imgsli::StoreObserver {
    Q_OBJECT

public:
    explicit Store(QObject* parent = nullptr);

    [[nodiscard]] QString stateJson() const;
    bool dispatch(const QString& actionJson);
    void on_rust_state_changed(
        rust::String stateJson,
        rust::String scope) override;

signals:
    void stateChanged(const QString& stateJson, const QString& scope);
    void dispatchFailed(const QString& message);

private:
    rust::Box<imgsli::RustStore> rustStore_;
};

}  // namespace imgsli::app
