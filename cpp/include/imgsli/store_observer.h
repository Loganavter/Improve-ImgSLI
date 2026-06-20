#pragma once

#include "rust/cxx.h"

namespace imgsli {

class StoreObserver {
public:
    virtual ~StoreObserver() = default;
    virtual void on_rust_state_changed(
        rust::String stateJson,
        rust::String scope) = 0;
};

}  // namespace imgsli
