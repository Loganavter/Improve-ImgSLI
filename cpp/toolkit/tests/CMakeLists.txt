# Toolkit unit tests, ported from `sli-ui-toolkit/tests/test_*.py`.
# Each test file declares a QObject subclass running under QTest. The
# helper below registers it as an executable + ctest entry.

function(add_toolkit_test name)
    add_executable(${name} ${name}.cpp)
    target_link_libraries(${name} PRIVATE
        sli_ui_toolkit_cpp
        Qt6::Core
        Qt6::Gui
        Qt6::Widgets
        Qt6::Test
    )
    add_test(NAME ${name} COMMAND ${name})
    # Tests poke QPainter so they need an offscreen Qt platform when running
    # under ctest in headless CI. The XDG_RUNTIME_DIR env var keeps QApplication
    # quiet about missing user runtime dirs on minimal environments.
    set_tests_properties(${name} PROPERTIES
        ENVIRONMENT "QT_QPA_PLATFORM=offscreen"
    )
endfunction()

add_toolkit_test(test_button_regions)
add_toolkit_test(test_button_custom_bg)
add_toolkit_test(test_button_toggle)
add_toolkit_test(test_button_underline)
add_toolkit_test(test_widgets_smoke)
add_toolkit_test(test_keyboard)
add_toolkit_test(test_theme)
add_toolkit_test(test_contrast)
add_toolkit_test(test_button_config_ctor)

# Cross-language parity tester. Builds the C++ renderer; the Python driver
# fires both renderers per case and pixel-diffs the PNGs.
add_executable(parity_renderer parity_renderer.cpp)
target_link_libraries(parity_renderer PRIVATE
    sli_ui_toolkit_cpp
    Qt6::Core
    Qt6::Gui
    Qt6::Widgets
)

find_package(Python3 COMPONENTS Interpreter)
if(Python3_Interpreter_FOUND)
    set(_parity_cases "${CMAKE_SOURCE_DIR}/../tests/parity/cases.json")
    set(_parity_pyrender "${CMAKE_SOURCE_DIR}/../tests/parity/python_renderer.py")
    set(_parity_runner "${CMAKE_SOURCE_DIR}/../tests/parity/run_parity.py")
    add_test(
        NAME parity_corpus
        COMMAND ${Python3_EXECUTABLE} ${_parity_runner}
    )
    set_tests_properties(parity_corpus PROPERTIES
        ENVIRONMENT
            "QT_QPA_PLATFORM=offscreen;IMGSLI_PARITY_CASES=${_parity_cases};IMGSLI_PARITY_CPP=$<TARGET_FILE:parity_renderer>;IMGSLI_PARITY_PYRENDER=${_parity_pyrender}"
    )
endif()

