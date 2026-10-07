# Contributing to ffsuite

Thank you for considering contributing to ffsuite: ffman, ffmeta and subverter.

## Prerequisites

- **Nix** with flakes. `nix develop` gives every tool at the flake's pin: Python, uv, ruff,
  basedpyright, just, dprint, cocogitto, pre-commit, and ffman's runtime (ffmpeg 8.1, FLAC
  1.5, which the tests hold it to). On NixOS, the wheels uv installs need
  `programs.nix-ld.enable`.
- **Without Nix**: uv, just, dprint, cocogitto and pre-commit on your `PATH`. The tests marked
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

Read [AGENTS.md](AGENTS.md) first: the layout, the checks, and the rules. Behaviour is the
contract: a change to what ffman does needs a line in its `CHANGELOG.md`, a test that fails on
the old behaviour, and a row in [`docs/decisions.md`](docs/decisions.md).

## Testing Strategy

- **Pure functions:** keep decisions apart from effects, and cover them with unit tests.
- **Regressions:** a bug fix comes with a test that reproduces the failure.
- **The outcome report:** a change to ffman's behaviour shows in
  `uv run python -m tests.outcome compare HEAD`, run from `packages/ffman` (AGENTS.md).

## Development Workflow

1. [Conventional Commits](https://www.conventionalcommits.org/) are enforced: by the
   `commit-msg` hook and by CI (`cog.toml`).
2. Run the checks. The `justfile` runs the workflows' commands:

```sh
just checks   # the lock, ruff, types, dead code, the suite and the matrix, dprint, cog, pip-audit
just nix      # the flake's checks, as nix.yml
just format   # ruff and dprint, in place
```

`just` alone lists every recipe.

## Creating a Pull Request

1. Make sure `just checks` passes.
2. Open a pull request against `main`. Describe the problem it solves, and link its issue
   (`Fixes #123`), if any.
3. Wait for a maintainer's review.

## Releasing (maintainers)

Each package is released on its own: `just release <ffman|ffmeta|subverter> <major|minor|patch>`,
from a clean `main` up to date with `origin`. It refuses a version below the package's own, runs
`just checks`, and lets cocogitto set the version (`uv version`, the lock) and commit it. It then
tags `<package>-v<version>` and pushes the commit and the tag together. The tag runs
`release.yml` (the GitHub release) and `publish.yml` (PyPI).

- A first release is `minor`: cocogitto counts from 0.0.0, so it gives 0.1.0, the version each
  package carries.
- Release a library before an ffman that needs it: ffman's wheel requires both libraries.
- ffman's range for each library must admit that library's version (`test_workspace`, which
  the bump runs). A library's minor release in 0.x leaves ffman's `<0.2`, so widen ffman's range
  first, in its own commit.
