# ffmeta, subverter and ffman, built from any nixpkgs: the flake's own, or a system's through
# overlays.default -- its ffmpeg-full then the system's (nixos-config's carries FDK). Each from
# its own pyproject.toml: name, version, description, licence, homepage, the Python it needs.
{
  pkgs,
  python3Packages ? pkgs.python3Packages,
}:
let
  inherit (pkgs) lib;

  # One workspace member, as nixpkgs builds Python (a wheel by hatchling, installed by installer)
  # from the files its wheel takes; its tests run apart, from the root.
  member =
    buildPython: root: attrs:
    let
      project = (lib.importTOML (root + "/pyproject.toml")).project;
      # requires-python, a floor alone (">=3.13"): an older interpreter refused at evaluation
      floor = builtins.match ">=([0-9.]+)" project.requires-python;
      oldest = lib.throwIf (floor == null) "${project.name}: requires-python is no floor alone" (
        lib.head floor
      );
      # the SPDX expression's licence identifiers: its operators, parentheses and `WITH`
      # exceptions aside
      licences = lib.subtractLists [ "" "AND" "OR" ] (
        lib.filter lib.isString (builtins.split "[ ()]+|WITH [^ ()]+" project.license)
      );
    in
    buildPython (
      lib.recursiveUpdate {
        pname = project.name;
        inherit (project) version;
        src = lib.fileset.toSource {
          inherit root;
          fileset = lib.fileset.unions (
            map (path: root + "/${path}") [
              "pyproject.toml"
              "README.md"
              "LICENSE-MIT"
              "LICENSE-APACHE"
              "src"
            ]
          );
        };
        disabled = python3Packages.pythonOlder oldest;
        pyproject = true;
        build-system = [ python3Packages.hatchling ];
        doCheck = false;
        pythonImportsCheck = [ project.name ];
        meta = {
          inherit (project) description;
          homepage = project.urls.Homepage;
          license = map lib.getLicenseFromSpdxId licences;
        };
      } attrs
    );

  # THE TOOLS ffman RUNS, named once: exactly its wrapper's PATH -- the closure proves them.
  runtime = [
    pkgs.ffmpeg-full # ffmpeg ffprobe: ffman detects libfdk_aac, and without it uses native aac
    (pkgs.ffmpeg-normalize.override { ffmpeg = pkgs.ffmpeg-full; }) # ffmpeg-normalize: same ffmpeg
    pkgs.flac # metaflac: a source FLAC's CUESHEET block, carried
    pkgs.oxipng # oxipng: PNG outputs
    pkgs.jpegoptim # jpegoptim: JPEG outputs, lossless (--auto-mode)
    pkgs.gifsicle # gifsicle: GIF outputs, lossless (-O3)
    pkgs.coreutils # nproc: the thread count; env: ffmpeg-normalize's XDG_CONFIG_HOME
  ];

  # The wrapper's: PATH set, not prefixed -- ffman finds these tools and nothing else (its presets,
  # like its fonts, in its package).
  wrapperArgs = tools: [
    "--set"
    "PATH"
    (lib.makeBinPath tools)
  ];

  ffmeta = member python3Packages.buildPythonPackage ../packages/ffmeta { };
  subverter = member python3Packages.buildPythonPackage ../packages/subverter { };
  ffman = member python3Packages.buildPythonApplication ../packages/ffman {
    dependencies = [
      ffmeta
      subverter
    ];
    makeWrapperArgs = wrapperArgs runtime;
    # the checks' and the dev shell's; wrapperArgs, a wrapper over other tools (overridePythonAttrs)
    passthru = { inherit runtime wrapperArgs; };
    meta.mainProgram = "ffman";
  };
in
{
  inherit ffmeta subverter ffman;
}
