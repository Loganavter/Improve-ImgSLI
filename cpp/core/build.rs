fn main() {
    cxx_build::bridge("src/bridge.rs")
        .include("../include")
        .std("c++20")
        .compile("imgsli_core_bridge");
    println!("cargo:rerun-if-changed=src/bridge.rs");
    println!("cargo:rerun-if-changed=src/lib.rs");
}
