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
      # rest, a system's own: overlays.default's ffman-image) -- for the image alone: "nonfree and
      # unredistributable" (ffmpeg's configure), built, never published
      tuned =
        system:
        import nixpkgs {
          inherit system;
          config.allowUnfreePredicate = pkg: lib.getName pkg == "ffmpeg-full";
          overlays = [
            (_: prev: {
              ffmpeg-full = prev.ffmpeg-full.override { withUnfree = true; };
            })
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
          image = import ./nix/image.nix { pkgs = tuned pkgs.stdenv.hostPlatform.system; };
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

      # ffman and its image on the consumer's own nixpkgs: its ffmpeg-full, a system's tuned build
      overlays.default = final: _: {
        inherit (import ./nix/packages.nix { pkgs = final; }) ffman;
        ffman-image = import ./nix/image.nix { pkgs = final; };
      };

      checks = forAllSystems (pkgs: import ./nix/checks.nix { inherit pkgs; });

      devShells = forAllSystems (pkgs: {
        default = import ./nix/shell.nix { inherit pkgs; };
      });

      # `nix fmt`: nixfmt over the tree (nixfmt given a directory is deprecated, its own warning)
      formatter = forAllSystems (pkgs: pkgs.nixfmt-tree);
    };
}
