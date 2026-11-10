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
      # `nix flake check`: the test suite passes
      checks = forAll (pkgs: {
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
        };
        # Blender is large: only for the render tasks (phase 3)
        render = pkgs.mkShell {
          packages = [ pkgs.blender pkgs.libwebp ];
        };
      });
    };
}
