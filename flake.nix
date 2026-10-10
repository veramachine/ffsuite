{
  description = "ffman: opinionated media conversion on ffmpeg; its libraries ffmeta, subverter";

  # nixos-config's channel: its flake takes this one with `inputs.nixpkgs.follows` (6.7.8)
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs =
    { self, nixpkgs }:
    let
      inherit (nixpkgs) lib;
      # nixos-config's, and Apple silicon's (Intel Macs' support ends with nixpkgs 26.05)
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];
      forAllSystems = f: lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
      # ffmpeg-full with FDK (withUnfree), the one tuning of the owner's system ffman reads (the
      # rest, a system's own: overlays.default's ffman-image) -- for `image` alone: "nonfree and
      # unredistributable" (ffmpeg's configure), built by its user, never published. The image is
      # the overlay's, so the flake's and a consumer's are made alike.
      tuned =
        system:
        import nixpkgs {
          inherit system;
          config.allowUnfreePredicate = pkg: lib.getName pkg == "ffmpeg-full";
          overlays = [
            (_: prev: {
              ffmpeg-full = prev.ffmpeg-full.override { withUnfree = true; };
            })
            self.overlays.default
          ];
        };
    in
    {
      packages = forAllSystems (
        pkgs:
        let
          built = import ./nix/packages.nix { inherit pkgs; };
        in
        built
        // {
          default = built.ffman;
        }
        // lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {
          image = (tuned pkgs.stdenv.hostPlatform.system).ffman-image;
          # the published one (image.yml): this ffman, nixpkgs' ffmpeg-full -- no FDK (withUnfree
          # false, nixpkgs' default), every package free by nixpkgs' licences (decisions.md)
          image-free = import ./nix/image.nix {
            inherit pkgs;
            inherit (built) ffman;
          };
        }
      );

      # `nix run github:veramachine/ffsuite -- convert ...`
      apps = lib.mapAttrs (_: packages: {
        default = {
          type = "app";
          program = lib.getExe packages.ffman;
          meta.description = packages.ffman.meta.description;
        };
      }) self.packages;

      # ffman and its image on the consumer's own nixpkgs: its ffmpeg-full, a system's tuned build;
      # the image of final.ffman, so a consumer's override of ffman reaches it
      overlays.default = final: _: {
        inherit (import ./nix/packages.nix { pkgs = final; }) ffman;
        ffman-image = import ./nix/image.nix {
          pkgs = final;
          inherit (final) ffman;
        };
      };

      checks = forAllSystems (pkgs: import ./nix/checks.nix { inherit pkgs; });

      devShells = forAllSystems (pkgs: {
        default = import ./nix/shell.nix { inherit pkgs; };
      });

      # `nix fmt`: nixfmt over the tree (nixfmt given a directory is deprecated, its own warning)
      formatter = forAllSystems (pkgs: pkgs.nixfmt-tree);
    };
}
