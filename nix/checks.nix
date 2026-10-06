# The flake's checks. On each Python ffman supports: the tests (pytest from the root over its
# three trees, against the installed packages), the matrix, the installed binary
# (nix/installed.sh), types and dead code; once, interpreter-free: ruff, nixfmt, shellcheck.
{ pkgs }:
let
  inherit (pkgs) lib;

  # What the Python checks read: the workspace's configuration, its three packages -- their
  # trees and the sources they read themselves (test_architecture, test_imports, test_outcome),
  # their files (test_workspace, against the root's licences) -- and the skills (test_skills).
  # Lint reads the Nix files too; the Python checks do not, so an edit here reruns lint, not them.
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
      # third-party imports from this interpreter
      python = python3Packages.python.withPackages (ps: [
        ps.pytest
        ps.hypothesis
        ps.numpy
      ]);
    in
    lib.mapAttrs' (name: lib.nameValuePair "${name}-${suffix}") {
      tests = pytest "tests" [ "--cov" ] { disabledTestMarks = [ "slow" ]; };
      # each case renders: in parallel; a slice of the tests, so no coverage floor
      matrix = pytest "matrix" [
        "-n"
        "auto"
      ] { enabledTestMarks = [ "slow" ]; };
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
        basedpyright --pythonpath ${python}/bin/python
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
        shellcheck nix/*.sh
        touch $out
      '';
}
