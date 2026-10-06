# `nix develop`: uv on nixpkgs' Python -- its own downloads off; `uv sync --locked` installs the
# dev group, pinned to this nixpkgs' versions -- the other tools the checks and the workflows run,
# and ffman's runtime, as the checks give it. On NixOS, the wheels uv installs
# (numpy, basedpyright's node) need the common C++ runtime: programs.nix-ld.
{ pkgs }:
let
  inherit (import ./packages.nix { inherit pkgs; }) ffman;
  python = pkgs.python3;
in
pkgs.mkShell {
  packages = [
    python
    pkgs.uv
    pkgs.ruff
    pkgs.basedpyright
    pkgs.nixfmt
    pkgs.shellcheck
    pkgs.just
    pkgs.dprint
    pkgs.cocogitto
    pkgs.pre-commit
  ]
  ++ ffman.runtime;
  env = {
    UV_PYTHON = "${python}/bin/python";
    UV_PYTHON_DOWNLOADS = "never";
  };
}
