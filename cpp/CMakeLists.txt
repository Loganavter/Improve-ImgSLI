cmake_minimum_required(VERSION 3.24)
project(imgsli_cpp LANGUAGES CXX)
enable_testing()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(Qt6 6.7 REQUIRED COMPONENTS Core Gui GuiPrivate Widgets ShaderTools)

include(FetchContent)
FetchContent_Declare(
    Corrosion
    GIT_REPOSITORY https://github.com/corrosion-rs/corrosion.git
    GIT_TAG v0.5.1
)
FetchContent_MakeAvailable(Corrosion)

corrosion_import_crate(
    MANIFEST_PATH core/Cargo.toml
    CRATES imgsli_core
)

# cxx generates a C++ header + source per #[cxx::bridge] module.
# We let cxx-build produce them as part of the Rust build, and consume
# the generated headers from include path corrosion exposes.
corrosion_add_cxxbridge(imgsli_core_bridge
    CRATE imgsli_core
    FILES bridge.rs
)
target_include_directories(imgsli_core_bridge PUBLIC ${CMAKE_SOURCE_DIR}/include)

add_subdirectory(toolkit)
add_subdirectory(app)
