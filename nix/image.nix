# ffman as an OCI image, on whatever ffmpeg-full `pkgs` holds: `nix build .#image`, then
# `./result | docker load` (a stream: no tarball kept in the store). Linux's alone.
{ pkgs }:
let
  inherit (pkgs) lib;
  inherit (import ./packages.nix { inherit pkgs; }) ffman;
in
pkgs.dockerTools.streamLayeredImage {
  name = "ffman";
  tag = ffman.version;
  # /tmp: the work directory's (TMPDIR unset); the sticky bit, as any /tmp, for any --user
  extraCommands = "mkdir -m 1777 tmp";
  config = {
    # tini as PID 1: it reaps what ffman's tools orphan and passes signals on, which ffman
    # (its own handlers: INT, TERM, HUP) turns into its cleanup
    Entrypoint = [
      (lib.getExe pkgs.tini)
      "--"
      (lib.getExe ffman)
    ];
    WorkingDir = "/work"; # the folder mounted: docker run -v "$PWD:/work"
    Env = [ "HOME=/tmp" ]; # writable for any --user
  };
}
