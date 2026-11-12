{
  description = "podglass: AirPods Pro 2 integration for NixOS + Hyprland (serpantinum shell)";

  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
      pythonFor = pkgs: pkgs.python3.withPackages (ps: [ ps.bleak ps.dbus-fast ps.cryptography ps.pytest ]);
    in
    {
      packages = forAll (pkgs: rec {
        podglass = pkgs.callPackage ./nix/package.nix { };
        default = podglass;
      });

      homeManagerModules.default = import ./nix/hm-module.nix self;

      # `nix flake check`: the package builds and the test suite passes
      checks = forAll (pkgs: {
        package = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
        tests = pkgs.runCommand "podglass-tests" { nativeBuildInputs = [ (pythonFor pkgs) ]; } ''
          cp -r ${pkgs.lib.cleanSource ./.} src && chmod -R u+w src && cd src
          export HOME=$TMPDIR
          python -m pytest -q -p no:cacheprovider tests || [ $? = 5 ]
          touch $out
        '';
      });

      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = [ (pythonFor pkgs) pkgs.quickshell pkgs.playerctl pkgs.libwebp pkgs.libnotify ];
          # WebP reader for the card's animated renders (AnimatedImage)
          QT_PLUGIN_PATH = "${pkgs.qt6.qtimageformats}/lib/qt-6/plugins";
        };
        # Blender is large: only for the render tasks (phase 3)
        render =
          let
            pkgsCuda = import nixpkgs {
              system = pkgs.stdenv.hostPlatform.system;
              config = { allowUnfree = true; cudaSupport = true; };
            };
          in
          pkgs.mkShell {
            packages = [ pkgsCuda.blender pkgs.libwebp pkgsCuda.cudaPackages.cuda_nvcc pkgs.gcc ];
            # Pascal (GTX 1060) has no prebuilt Cycles kernels: Blender compiles them with nvcc
            buildInputs = [ pkgsCuda.cudaPackages.cuda_cudart pkgsCuda.cudaPackages.cuda_cccl ];
          };
      });
    };
}
