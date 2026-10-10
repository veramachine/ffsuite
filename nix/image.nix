# ffman as a container image, the ffman given; Linux's alone. The flake's `image` (FDK's ffmpeg:
# yours to build, never published), `image-free` (nixpkgs' own: image.yml publishes it), the
# overlay's `ffman-image` (final.ffman).
#   nix build .#image          the gzipped docker-archive: `docker load < result`
#   nix build .#image.stream   the script that streams it uncompressed: `./result | docker load`,
#                              no second copy of the closure in the store
{ pkgs, ffman }:
let
  inherit (pkgs) lib;
in
pkgs.dockerTools.buildLayeredImage {
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
    # what GHCR reads (docs.github.com, "Working with the Container registry"): the source links
    # the package to its repository. No licences label: ffman's would misstate ffmpeg's
    Labels = {
      "org.opencontainers.image.title" = ffman.pname;
      "org.opencontainers.image.description" = ffman.meta.description;
      "org.opencontainers.image.version" = ffman.version;
      "org.opencontainers.image.source" = ffman.repository;
    };
  };
  # tini and the image are Linux's: the flake has no `.#image` elsewhere, and the overlay's
  # `ffman-image` is refused by name (its `.stream`, given no meta by buildLayeredImage, through
  # tini)
  meta.platforms = lib.platforms.linux;
}
