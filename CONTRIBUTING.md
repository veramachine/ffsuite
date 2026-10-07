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
  suite as GitHub's `checks.yml` does: `uv run pytest -m "not ffmpeg and not slow"`.

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
just checks   # the lock, ruff, types, dead code, the suite and the matrix, dprint, cog, pip-audit
just nix      # the flake's checks, as nix.yml
just format   # ruff and dprint, in place
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
from a clean `main` up to date with `origin`. It refuses a version below the package's own, runs
`just checks`, and lets cocogitto set the version (`uv version`, the lock), write the package's
`CHANGELOG.md` (git-cliff, `cliff.toml`) and commit both. It then tags `<package>-v<version>`
and pushes the commit and the tag together. The tag runs `release.yml` (the GitHub release, its
notes the changelog's new section) and `publish.yml` (PyPI).
`just changelog <package> --unreleased` shows that section before the release.

- A first release is `minor`: cocogitto counts from 0.0.0, so it gives 0.1.0, the version each
  package carries.
- Release a library before an ffman that needs it: ffman's wheel requires both libraries.
- ffman's range for each library must admit that library's version (`test_workspace`, which
  the bump runs). A library's minor release in 0.x leaves ffman's `<0.2`, so widen ffman's range
  first, in its own commit.
