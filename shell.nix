let
  # We pin to a specific nixpkgs commit for reproducibility.
  # Last updated: 2025-03-31 15:00UTC.
  pkgs =
    import
      (fetchTarball "https://github.com/NixOS/nixpkgs/archive/eb0e0f21f15c559d2ac7633dc81d079d1caf5f5f.tar.gz")
      { };
in
pkgs.mkShell {
  packages = [
    (pkgs.python313.withPackages (
      python-pkgs: with python-pkgs; [
        # select Python packages here
        pillow
        pyqt6
        pyqt6-sip
      ]
    ))
  ];
}
