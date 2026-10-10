# Contributing to ffsuite

Thank you for considering contributing to ffsuite: ffman, ffmeta and subverter.

## Prerequisites

- **Nix** with flakes. `nix develop` gives every tool at the flake's pin: Python, uv, ruff,
  basedpyright, just, dprint, cocogitto, pre-commit, and ffman's runtime (ffmpeg 8.1, FLAC
  1.5, which the tests hold it to). Run the checks in it. On NixOS, the wheels' executables
  (ruff, ty, basedpyright's node) need `programs.nix-ld.enable`; numpy's libraries come from the
  shell.
- **Without Nix**: uv 0.11.21 (`pyproject.toml`'s `required-version`: nixpkgs', as every pin
  here), just, dprint, cocogitto and pre-commit on your `PATH`. The tests marked
  `ffmpeg` need ffmpeg 8.1 and metaflac 1.5, which `just checks` runs. Without them, run the
  suite as GitHub's `checks.yml` does: `uv run pytest -m "not ffmpeg and not slow"`. `just
  checks` ends with the flake's checks, so without Nix it stops there, every other check passed.

## Setup

1. Fork this repository and create your branch from `main`.
2. Clone your fork, enter the shell, install the environment and the hooks:

```sh
git clone https://github.com/<you>/ffsuite && cd ffsuite
nix develop
uv sync --locked
pre-commit install   # ruff, dprint, the lock; the commit message
```

## Architecture and Guidelines

Read [AGENTS.md](AGENTS.md) first: the layout, the checks, and the rules -- the first of them,
that ffman's behaviour is its contract.

## Testing Strategy

- **Pure functions:** keep decisions apart from effects, and cover them with unit tests.
- **Regressions:** a bug fix comes with a test that reproduces the failure.
- **The outcome report:** a change to ffman's behaviour shows in
  `uv run python -m tests.outcome compare HEAD`, run from `packages/ffman` (AGENTS.md).

## Development Workflow

1. [Conventional Commits](https://www.conventionalcommits.org/) are enforced: by the
   `commit-msg` hook and by CI (`cog.toml`). A commit's subject is its changelog entry --
   git-cliff writes each package's `CHANGELOG.md` from the commits touching it, at its release
   -- so write it for that package's users.
2. Run the checks. The `justfile` runs the workflows' commands:

```sh
just checks   # the lock, ruff, types, dead code, the suite and the matrix, dprint, cog, pip-audit,
              # then `just nix`
just nix      # the flake's checks alone, as nix.yml: git's files only -- `git add` a new one
just format   # ruff and dprint, in place
just build    # each package's sdist and wheel, into dist/ (the root itself is no package)
```

`just` alone lists every recipe.

## Creating a Pull Request

1. Make sure `just checks` passes.
2. Open a pull request against `main`, titled as a conventional commit: a squash merge makes the
   title its commit, and so a changelog entry (CI checks it). Describe the problem it solves, and
   link its issue (`Fixes #123`), if any.
3. Wait for a maintainer's review.

## Releasing (maintainers)

Each package is released on its own: `just release <ffman|ffmeta|subverter> <major|minor|patch>`,
from a clean `main` equal to `origin/main`. It runs no tests: push first and release once CI is
green on that commit. It refuses a version not above the package's own, or a package whose current
version's tag is not on `origin`, and lets cocogitto set the version (`uv version`, the lock), write
the package's `CHANGELOG.md` (git-cliff, `cliff.toml`) and commit both. It then tags
`<package>-v<version>` and pushes the commit and that tag together. The tag runs `publish.yml`: the
package built once, published to PyPI, then its GitHub release of the same files, its notes the
changelog's new section. `just changelog <package> --unreleased` shows that section before the
release.

- Each package's 0.1.0 was published by hand (from 89d5487). Before the first `just release`, tag it
  `<package>-v0.1.0`, annotated, at the last commit touching its folder before 89d5487, which builds
  the same files byte for byte -- ffman 33b6f55, ffmeta 71688f8, subverter 6827d02 -- and push the
  three tags with the workflows `Publish` and `Release` disabled (`gh workflow disable`, then
  `enable`): PyPI holds their files, and a tag runs the workflows of its own commit, where
  `release.yml` still stands (gone from `main`, gh may not find it to disable: left on, it fails
  there, releasing nothing -- no changelog yet). cocogitto counts from a package's latest tag, and
  git-cliff's `--include-path` sees only commits touching the package: a tag elsewhere is lost.
- Release a library before an ffman that needs it: ffman's wheel requires both libraries. For
  ffman, the release refuses a library whose source is not its latest release's, and a floor in
  ffman's range below that release, patch included -- ffman is tested with it alone, and pip keeps
  an older one installed that the range admits.
- A library's release refuses a version ffman's range excludes (uv's lock ignores the range): a
  minor release in 0.x leaves ffman's `<0.2`, so widen ffman's range first, in its own commit; after
  the release, raise its floor to it.
