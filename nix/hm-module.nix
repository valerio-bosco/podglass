self:
{ config, lib, pkgs, ... }:

let
  cfg = config.programs.podglass;
  toml = pkgs.formats.toml { };
  settings = cfg.settings // lib.optionalAttrs cfg.batteryWidget { battery_widget = true; };
  configFile = toml.generate "podglass-config.toml" settings;
in
{
  options.programs.podglass = {
    enable = lib.mkEnableOption "podglass, AirPods Pro 2 integration (daemon and Quickshell UI)";

    package = lib.mkOption {
      type = lib.types.package;
      default = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
      defaultText = lib.literalMD "the podglass flake package";
      description = "The podglass package.";
    };

    settings = lib.mkOption {
      type = toml.type;
      default = { };
      example = lib.literalExpression ''
        {
          autoconnect = "in-ear";   # in-ear, lid-open or never
          ear_pause = true;
          theme = "auto";           # auto, light or dark
        }
      '';
      description = "Written to ~/.config/podglass/config.toml (keys: see podglass/config.py).";
    };

    batteryWidget = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Show the optional battery widget on the desktop (sets `battery_widget = true`).";
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = [ cfg.package ];
    xdg.configFile."podglass/config.toml" = lib.mkIf (settings != { }) { source = configFile; };

    # stem presses reach the media players only through mpris-proxy
    services.mpris-proxy.enable = lib.mkDefault true;

    systemd.user.services = {
      podglass = {
        Unit = {
          Description = "podglass AirPods daemon";
          # graphical-session.target too: see the note in oring's module (ordering cycle otherwise)
          After = [ "graphical-session.target" "bluetooth.target" ];
          PartOf = [ "graphical-session.target" ];
          X-Restart-Triggers = [ "${configFile}" ];
        };
        Service = {
          ExecStart = "${cfg.package}/bin/podglass daemon";
          Restart = "on-failure";
          # session tools the daemon calls (hyprctl needs the Hyprland instance variables
          # that the compositor imports into the user manager)
          Environment = [ "PATH=/run/wrappers/bin:/etc/profiles/per-user/${config.home.username}/bin:/run/current-system/sw/bin" ];
        };
        Install.WantedBy = [ "graphical-session.target" ];
      };
      podglass-ui = {
        Unit = {
          Description = "podglass UI (Quickshell)";
          After = [ "graphical-session.target" "podglass.service" ];
          PartOf = [ "graphical-session.target" ];
        };
        Service = {
          ExecStart = "${cfg.package}/bin/podglass ui";
          Restart = "on-failure";
        };
        Install.WantedBy = [ "graphical-session.target" ];
      };
    };
  };
}
