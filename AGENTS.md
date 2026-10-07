# Working on ffsuite

The workspace (uv's, its root no project of its own) of three packages under `packages/`:
ffman, the command line, and its libraries ffmeta and subverter. Read ffman's
[`README.md`](packages/ffman/README.md) for what it does, the spec
([`ffman-spec.md`](docs/ffman-spec.md)) for the command
line's contract, and [`docs/decisions.md`](docs/decisions.md) for
why each behaviour is what it is -- each row names the module it lives in.
The agent skills for the formats ffman reads and writes -- cue sheets,
ffmetadata, Vorbis comments -- are in [`.agents/skills/`](.agents/skills/README.md),
with their rules; ffmeta's tests read them as oracles.

## Layout

| Path                                                           | What                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| -------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `packages/ffman/src/ffman/cli.py`, `options.py`, `__main__.py` | the command line: the option registry and its parser; the entry, Windows refused first                                                                                                                                                                                                                                                                                                                                                                                        |
| `packages/ffman/src/ffman/jobs/`                               | `convert/`: one module a flow, chosen by `dispatch.py`; the effects' `passes.py`, the `render.py`, the `output.py` they share; `carried.py` the folders the package carries (fonts, presets); `options.py` validates the command line                                                                                                                                                                                                                                         |
| `packages/ffman/src/ffman/plan/`                               | the pure decisions: the flow, the outputs, the streams, YouTube; sizes (`geometry.py`), encoders (`encode.py`); what a job asks (`request.py`)                                                                                                                                                                                                                                                                                                                                |
| `packages/ffman/src/ffman/effects/`                            | the effects: the registry (`__init__.py`), one module an effect, their stages (`stages.py`)                                                                                                                                                                                                                                                                                                                                                                                   |
| `packages/ffman/src/ffman/subs/`                               | transcripts in (`ingest.py`, through subverter's readers; `normalize.py`), placement (`layout.py`), ASS and SRT out                                                                                                                                                                                                                                                                                                                                                           |
| `packages/ffmeta/src/ffmeta/`                                  | ffmeta, its own package: metadata files (ffmetadata, Vorbis comments, cue sheets): their one model (`model.py`: tags as written, exact times, a cue's disc); one module a format (`ffmetadata.py`, `vorbis.py`, `cue.py`), `convert.py` between them, `fields.py` the one table both map by, `files.py` a file's format by its name, `edit.py` `meta`'s edits, `chapters.py` its chapters, `time.py` its one time syntax; `_errors.py` its refusal, `_values.py` its rounding |
| `packages/subverter/src/subverter/`                            | subverter, its own package: transcripts read into one model -- `readers/` one module a format, `transcript.py` the types, `markup.py` `untagged`; `_errors.py` its refusal, `_values.py` its rounding                                                                                                                                                                                                                                                                         |
| `packages/ffman/src/ffman/graph/`                              | filtergraphs, as data: the model, the resize, light, GIF; the sizes they read (`sizes.py`)                                                                                                                                                                                                                                                                                                                                                                                    |
| `packages/ffman/src/ffman/media/`                              | ffprobe's JSON (`probe.py`), running tools (`run.py`), paths (`paths.py`: file URLs, the partial file)                                                                                                                                                                                                                                                                                                                                                                        |
| `packages/ffman/src/ffman/errors.py`, `values.py`, `fmt.py`    | what all may use: the one error and `PROG`, `REFUSALS` (ffman's and its libraries': each worded `ffman: error:`), a refusal at a file's line, value checks, stage A's number text                                                                                                                                                                                                                                                                                             |
| `packages/ffman/tests/`                                        | ffman's unit and property tests; `suite/`, the bash suites ported (ids `S…`: run.sh's, `M…`: matrix.sh's); `test_workspace.py` and the outcome harness, the repository's own                                                                                                                                                                                                                                                                                                  |
| `packages/ffman/tests/support/`                                | ffman's shared measures (numpy), media helpers, Hypothesis strategies                                                                                                                                                                                                                                                                                                                                                                                                         |
| `packages/*/tests/`                                            | each library's own tests, no package (`--import-mode=importlib`): ffmeta's with `ffmeta_support` (strategies, examples, its oracles' tools) and the pinned-tool fixtures; subverter's; `test_imports.py` in each: itself and the standard library alone. One run from the root takes all three trees; each sdist runs its own                                                                                                                                                 |
| `flake.nix`, `nix/`                                            | the flake (Linux, Apple silicon): the packages (`packages.nix`: the runtime, the wrapper), the image (`image.nix`, Linux's: FDK's ffmpeg, never published), the checks (`checks.nix`; `installed.sh`, the installed binary's), the dev shell (`shell.nix`)                                                                                                                                                                                                                    |
| `justfile` `cog.toml` `dprint.json` `.pre-commit-config.yaml`  | the tooling (CONTRIBUTING.md): the checks and the release as recipes; Conventional Commits and the packages' tags; their changelogs, `cliff.toml` (git-cliff's); Markdown and TOML formatting; the hooks                                                                                                                                                                                                                                                                      |
| `.github/`                                                     | the workflows, each from its source (csan's, imi's); `package-tag.sh`, a package's tag read as its package (release's and publish's); Dependabot (GitHub Actions alone); the issue and pull request templates                                                                                                                                                                                                                                                                 |

## The checks

`nix develop` gives the toolchain at the flake's pin -- uv on nixpkgs' Python (its own
downloads off), ruff, basedpyright, nixfmt, shellcheck, just, dprint, cocogitto, pre-commit --
and ffman's runtime. In it, `uv sync --locked` once: the dev group, pinned to the
same nixpkgs' versions, so a uv run's verdict is Nix's (basedpyright resolves numpy's stubs, and
numpy 2.4's differ from 2.5's; ruff's `ALL` grows with each release). Then:

```sh
just ruff-checks   # lint and format
just vulture       # dead code: src only, [tool.vulture]
just static        # types: basedpyright blocks, ty advisory (never blocking)
just pytest        # the suite but the matrix: 100% line and branch
just matrix        # the matrix, in parallel
just checks        # all of these, and the lock, dprint, cog and pip-audit: the workflows'
```

Each recipe's command is in the `justfile`. `pre-commit install` adds the hooks: ruff, dprint
and the lock before a commit, and its message conventional (`cog.toml`).

On NixOS, the wheels' executables (ruff, ty, basedpyright's node) need `programs.nix-ld.enable`,
and numpy's libraries the dev shell's `LD_LIBRARY_PATH`: run the checks in it. Without Nix,
`uv sync --locked` gives the same tools, and ffmpeg and the runtime are the host's (the tests that
run ffmpeg and metaflac hold them to the pins' 8.1 and 1.5; `-m "not ffmpeg"` leaves each out, the
conftests marking every test that takes either fixture). `nix fmt` formats the Nix files.

`nix flake check` (`just nix`) runs the same, each on Python 3.13 and 3.14 (pytest against the
installed packages): `tests-*`, `matrix-*`, `types-*`, `vulture-*`, and `installed-*` -- the built
binary through its wrapper alone (`nix/installed.sh`), which nothing else reaches: the suite calls
`main()` in-process; `lint` once (ruff, nixfmt, shellcheck: no interpreter); `pins`, every pin in
the dependency groups, and uv's `required-version`, this nixpkgs' version -- Dependabot moves none
of them. At a nixpkgs bump,
the tools' behaviour ffman holds to, re-checked: [`docs/upgrading.md`](docs/upgrading.md).

GitHub runs them too (`.github/workflows/`): `checks.yml`, the dev group's tools on 3.13 and 3.14
without ffmpeg (`-m "not ffmpeg and not slow"`; ty advisory) and `uv lock --check`; `nix.yml`,
`nix flake check` built on x86_64 and aarch64 Linux and Apple silicon and evaluated for all three
at once, and on a pull request the outcome report against its base; `security.yml`, pip-audit over
the lock, daily; on a package's tag (`ffmeta-v0.2.0`), `release.yml` and `publish.yml`: its GitHub
release, and PyPI through Trusted Publishing. `just release` cuts that tag, the package's
`CHANGELOG.md` written by git-cliff (CONTRIBUTING.md).

## The outcome report

What ffman does, recorded, so a change shows exactly what it changes (phase 6's
proof: [`ffman-phase6.md`](docs/ffman-phase6.md)). In the dev
shell, from `packages/ffman`:

```sh
uv run python -m tests.outcome compare HEAD   # HEAD's src and this tree's: identical, same graph, or changed
```

It runs a fixed corpus (`packages/ffman/tests/outcome/corpus.py`: 427 cases, every flow, effect,
transcript and refusal) under `--dry-run` and records each case's exit status,
stdout (the commands), stderr (notes, refusals) and work files (the ASS and SRT
ffman writes) -- not pixels, which are the suite's. "Same graph": a filtergraph
whose text differs where ffmpeg reads it the same. Exit 1 on any change, each
one's diff printed; `report SRC OUT` and `diff OLD NEW` are its halves. It
fails, never records, when it cannot vouch for a case: a work directory printed
but not captured, a capture that fails, a `src` without its `pyproject.toml`, a path it cannot
name (beyond `[A-Za-z0-9._/-]`: a checkout's `ffsuite (1)`).
Its burns measure their lines by ffman's own fonts, copied from `ffman/fonts`:
the same on every machine.

Its reach, measured (coverage over every case): 96% of `src`. The rest is what
`--dry-run` cannot reach -- real writes and partial files, signals and process
groups, a tool that fails, an ffmpeg without an encoder, ffprobe's non-JSON --
internal invariants, and the camcorder's clock fallback (a case there would
read the clock). Each case runs under `python -S`: the commit's own code and
`pyproject.toml`, never an installed ffman. A new path ffman gains needs a case:
measure again when the corpus or the code changes. A branch within one line (a
conditional expression) is invisible to coverage: find its cases by their output.

## Rules

- **Behaviour is the contract.** A change to what ffman does needs a `feat` or
  `fix` commit whose subject states it -- its changelog entry: git-cliff writes
  each package's `CHANGELOG.md` from its commits at a release, never by hand --
  a test that fails on the old behaviour, and a `docs/decisions.md` row (the
  plan's G4). The port's own changes from the bash ffman: `docs/ffman-from-bash.md`.
- **Layers** (plan §3): imports point down, never in a cycle; only the media
  layer starts processes; planners and graphs touch no file --
  `packages/ffman/tests/test_architecture.py` holds them; a new module gets a layer there, and
  a move that closes an exception strikes it.
- **Runtime: the standard library only.** External tools come through
  `PATH`, which the wrapper sets to `runtime` (`nix/packages.nix`) and
  nothing else: a new tool joins that list, and a job in `nix/installed.sh`.
- **Types are complete** (`typeCheckingMode = "all"`, failing on warnings).
  `Any` stays at a boundary and is narrowed at once: ffprobe's and the
  transcripts' JSON (`media/probe.py`, `subverter/readers/whisper.py`), and typeshed's own (one, in
  `cli.py`).
- **Constants carry provenance**: a measured or sourced number is a named
  constant with its source.
- **NumPy is for the tests.** Its stubs (2.4) type a reduction, an index and a
  power as `Any`: cast where the value is made, or use the typed helpers in
  `packages/ffman/tests/support/measures.py`.
- **Coverage 100%**, line and branch, with no exclusions (the floor in
  `pyproject.toml` is 95).
- **A warning fails the suite** (`filterwarnings = ["error"]`): a pipe or file a
  test opens is closed -- `subprocess.Popen` as a context manager. A leaked pipe
  went unseen until it was made so.
- **Tests run in the Nix sandbox**: no network, no writable `HOME`, no
  `/usr/bin/env` -- a script a test writes begins `#!/bin/sh`, or is bypassed
  silently.
- **Markers**: `ffmpeg`, a pinned tool needed (ffmpeg, metaflac) -- by hand, or by the fixture a
  test takes (the conftests); `slow`, the combination matrix (its own
  check). A marked test's parameter ids are the bash checks they port.
- **Documents**: no badges in a README (the owner's). dprint's plugins are pinned by version in
  `dprint.json`, as every tool, but kept at their latest releases, not nixpkgs' (the owner's):
  `just dprint-update`.
