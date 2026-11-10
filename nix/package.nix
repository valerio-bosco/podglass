{ lib, stdenvNoCC, makeWrapper, python3, quickshell, playerctl, wireplumber, hyprland, libnotify }:

let
  python = python3.withPackages (ps: [ ps.bleak ps.dbus-fast ps.cryptography ]);
  # used by the daemon: media control, volume (wpctl), window info (hyprctl), notifications
  runtimeTools = [ playerctl wireplumber hyprland libnotify ];
in
stdenvNoCC.mkDerivation {
  pname = "podglass";
  version = "0.1.0";
  src = lib.cleanSource ../.;

  nativeBuildInputs = [ makeWrapper ];

  installPhase = ''
    runHook preInstall
    share=$out/share/podglass
    mkdir -p $share/assets $share/tools $out/bin
    cp -r podglass ui $share/
    cp -r assets/placeholder $share/assets/
    cp tools/demo_state.py $share/tools/
    find $share -name __pycache__ -type d -prune -exec rm -rf {} +
    makeWrapper ${python}/bin/python $out/bin/podglass \
      --add-flags "-m podglass" \
      --set PYTHONPATH $share \
      --set PODGLASS_ROOT $share \
      --set PODGLASS_BIN $out/bin/podglass \
      --set PODGLASS_PYTHON ${python}/bin/python \
      --set-default PODGLASS_QUICKSHELL ${quickshell}/bin/quickshell \
      --suffix PATH : ${lib.makeBinPath runtimeTools}
    runHook postInstall
  '';

  meta = {
    description = "AirPods Pro 2 integration for NixOS + Hyprland (daemon and Quickshell UI)";
    license = lib.licenses.gpl3Plus;
    platforms = lib.platforms.linux;
    mainProgram = "podglass";
  };
}
