# The flake's checks. On each Python ffman supports: the tests (pytest from the root over its
# three trees, against the installed packages), the matrix, the installed binary
# (nix/installed.sh), types and dead code; once, interpreter-free: ruff, nixfmt, shellcheck, and
# the dependency groups' pins held to this nixpkgs.
{ pkgs }:
let
  inherit (pkgs) lib;

  # What the Python checks read: the workspace's configuration, its three packages -- their
  # trees and the sources they read themselves (test_architecture, test_imports, test_outcome),
  # their files (test_workspace, against the root's licences) -- and the skills (test_skills).
  # Lint reads the Nix files and the workflows' script too; the Python checks do not, so an edit
  # there reruns lint, not them.
  pythonFiles = [
    ../pyproject.toml
    ../LICENSE-MIT
    ../LICENSE-APACHE
    ../packages
    ../.agents/skills
  ];
  sourceOf =
    files:
    lib.fileset.toSource {
      root = ../.;
      fileset = lib.fileset.unions files;
    };
  source = sourceOf pythonFiles;
  lintSource = sourceOf (
    pythonFiles
    ++ [
      ../flake.nix
      ../nix
      ../.github/package-tag.sh
    ]
  );

  onPython =
    suffix: python3Packages:
    let
      inherit (import ./packages.nix { inherit pkgs python3Packages; }) ffman;
      # pytest over the installed packages, as pytestCheckHook runs it: ffman built from its own
      # source, the tests run from the workspace's root (a writable copy: coverage and Hypothesis
      # write there); no .pytest_cache, nothing kept between builds
      pytest =
        kind: flags: marks:
        ffman.overridePythonAttrs (
          {
            pname = "ffman-${kind}";
            doCheck = true;
            preCheck = ''
              cp -r ${source} "$NIX_BUILD_TOP/workspace"
              chmod -R u+w "$NIX_BUILD_TOP/workspace"
              cd "$NIX_BUILD_TOP/workspace"
            '';
            nativeCheckInputs = [
              python3Packages.pytestCheckHook
              python3Packages.pytest-cov
              python3Packages.pytest-timeout # pyproject's timeout, under --strict-config
              python3Packages.pytest-xdist
              python3Packages.hypothesis
              python3Packages.numpy
              pkgs.unixtools.ps # the signal tests' process table (tests/support/processes.py)
            ]
            ++ ffman.runtime; # metaflac among them: ffmeta's oracle too
            pytestFlags = [
              "-p"
              "no:cacheprovider"
            ]
            ++ flags;
          }
          // marks
        );
      lean = ffman.overridePythonAttrs {
        makeWrapperArgs = ffman.wrapperArgs (
          lib.subtractLists [ pkgs.oxipng pkgs.jpegoptim pkgs.gifsicle ] ffman.runtime
        );
      };
      # basedpyright resolves the workspace from the tree (pyproject's extraPaths); the tests'
      # third-party imports from this interpreter, analysed as its version -- pyproject's
      # pythonVersion is the floor, which `just static` checks
      python = python3Packages.python.withPackages (ps: [
        ps.pytest
        ps.hypothesis
        ps.numpy
      ]);
    in
    lib.mapAttrs' (name: lib.nameValuePair "${name}-${suffix}") {
      # each on the build's cores: pytest-xdist's setup hook adds --numprocesses=$NIX_BUILD_CORES
      # to a pytestCheckHook run that has it (nixpkgs' pytest-xdist/setup-hook.sh)
      tests = pytest "tests" [ "--cov" ] { disabledTestMarks = [ "slow" ]; };
      # a slice of the tests, so no coverage floor
      matrix = pytest "matrix" [ ] { enabledTestMarks = [ "slow" ]; };
      installed =
        pkgs.runCommand "installed-${suffix}"
          {
            nativeBuildInputs = [
              pkgs.ffmpeg-full
              pkgs.flac # the source's CUESHEET block made, and the output's read
            ];
            ffman = lib.getExe ffman;
            lean = lib.getExe lean;
          }
          ''
            bash ${./installed.sh}
            touch $out
          '';
      types = pkgs.runCommand "types-${suffix}" { nativeBuildInputs = [ pkgs.basedpyright ]; } ''
        export HOME=$TMPDIR
        cd ${source}
        basedpyright --pythonpath ${python}/bin/python --pythonversion ${python3Packages.python.pythonVersion}
        touch $out
      '';
      vulture =
        pkgs.runCommand "vulture-${suffix}" { nativeBuildInputs = [ python3Packages.vulture ]; }
          ''
            cd ${source}
            vulture
            touch $out
          '';
    };
in
onPython "py313" pkgs.python313Packages
// onPython "py314" pkgs.python314Packages
// {
  lint =
    pkgs.runCommand "lint"
      {
        nativeBuildInputs = [
          pkgs.ruff
          pkgs.nixfmt
          pkgs.shellcheck
        ];
      }
      ''
        cd ${lintSource}
        ruff check --no-cache .
        ruff format --check --no-cache .
        nixfmt --check flake.nix nix/*.nix
        shellcheck nix/*.sh .github/package-tag.sh
        touch $out
      '';

  # Every pin in pyproject.toml's dependency groups, and uv's required version, is this nixpkgs'
  # version, so uv's verdict is Nix's; no Dependabot moves them (.github/dependabot.yml): a nixpkgs
  # bump that leaves one behind fails here (docs/upgrading.md). Each from python3Packages, but
  # nixpkgs' applications.
  pins =
    let
      applications = {
        inherit (pkgs)
          basedpyright
          ruff
          ty
          pip-audit
          git-cliff
          uv
          ;
      };
      nixpkgsVersion = name: (applications.${name} or pkgs.python3Packages.${name}).version;
      pin =
        spec:
        let
          parts = lib.splitString "==" spec;
        in
        lib.throwIfNot (lib.length parts == 2) "pyproject.toml: ${spec} is no name==version" {
          name = lib.head parts;
          version = lib.last parts;
        };
      pyproject = lib.importTOML ../pyproject.toml;
      uv = {
        name = "uv";
        version = lib.removePrefix "==" pyproject.tool.uv.required-version;
      };
      stale = lib.filter (p: nixpkgsVersion p.name != p.version) (
        [ uv ] ++ map pin (lib.concatLists (lib.attrValues pyproject.dependency-groups))
      );
    in
    pkgs.runCommand "pins"
      {
        stale = lib.concatMapStringsSep "\n" (
          p: "${p.name}: pinned ${p.version}, nixpkgs ${nixpkgsVersion p.name}"
        ) stale;
      }
      ''
        if [ -n "$stale" ]; then
          printf '%s\n' "$stale" >&2
          exit 1
        fi
        touch $out
      '';
}
