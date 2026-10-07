# `nix develop`: uv on nixpkgs' Python -- its own downloads off; `uv sync --locked` installs the
# dev group, pinned to this nixpkgs' versions -- the other tools the checks and the workflows run,
# and ffman's runtime, as the checks give it. On NixOS, the wheels' executables (ruff, ty,
# basedpyright's node) ask for /lib64/ld-linux-x86-64.so.2: programs.nix-ld.
{ pkgs }:
let
  inherit (pkgs) lib;
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
  }
  // lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {
    # numpy's wheel takes libstdc++, libgcc_s and (its libgfortran's) libz from the system, which
    # nixpkgs' Python's loader never searches; nix-ld's NIX_LD_LIBRARY_PATH serves its foreign
    # executables alone (measured: "libstdc++.so.6: cannot open shared object file" on NixOS
    # with nix-ld on). This nixpkgs' own, as its programs here link
    LD_LIBRARY_PATH = lib.makeLibraryPath [
      pkgs.stdenv.cc.cc.lib
      pkgs.zlib
    ];
  };
}
