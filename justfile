# csan's Justfile for the workspace, its groups and aliases, with imi's `checks`, `cog`,
# `dprint-check`, `audit` and `release`. The commands are the workflows' (.github/workflows/):
# `just checks` runs checks.yml's -- in the dev shell with every test, ffmpeg's and the matrix --
# the style checks' and security.yml's; `just nix` runs nix.yml's. Run them in `nix develop`.

alias check := checks
alias fmt := format
alias linter := lint
alias lints := lint
alias ruff-check := ruff-checks
alias test := pytest
alias tests := pytest
alias typing := static

[doc("List the recipes")]
[group("Misc")]
default:
    @just --list --unsorted

[doc("Format the code, the Markdown and the TOML (modifies files)")]
[group("Format")]
format:
    uv run --locked ruff format
    dprint fmt

[doc("Check the code's format")]
[group("Checks")]
[group("Ruff")]
format-check:
    uv run --locked ruff format --check

[doc("Run the linter (modifies nothing)")]
[group("Checks")]
[group("Ruff")]
lint:
    uv run --locked ruff check

[doc("format-check and lint")]
[group("Checks")]
[group("Ruff")]
ruff-checks: format-check lint

[doc("Types: basedpyright blocks; ty is advisory, its failure ignored")]
[group("Checks")]
static:
    uv run --locked basedpyright
    -uv run --locked ty check

[doc("Dead code in the packages' sources")]
[group("Checks")]
vulture:
    uv run --locked vulture

[doc("The suite but the matrix, with its coverage")]
[group("Checks")]
[group("Tests")]
pytest:
    uv run --locked pytest -m "not slow" --cov -n auto

[doc("The combination matrix")]
[group("Checks")]
[group("Tests")]
matrix:
    uv run --locked pytest -m slow -n auto

[doc("The lock matches the pyproject files")]
[group("Checks")]
lock-check:
    uv lock --check

[doc("Markdown and TOML formatted (dprint.json)")]
[group("Checks")]
[group("Style")]
dprint-check:
    dprint check

[doc("dprint's plugins to their latest (dprint.json), then the Markdown and TOML rechecked")]
[group("Style")]
dprint-update:
    dprint config update
    dprint check

[doc("Every commit conventional (cog.toml)")]
[group("Checks")]
[group("Style")]
cog:
    cog check

[doc("pip-audit over the lock, exported")]
[group("Checks")]
audit:
    #!/usr/bin/env bash
    set -euo pipefail
    requirements=$(mktemp)
    trap 'rm -f "$requirements"' EXIT
    uv export --locked --all-packages --all-groups --no-emit-workspace \
        --format requirements.txt --quiet --output-file "$requirements"
    uv run --locked --isolated --only-group audit \
        pip-audit --strict --disable-pip --require-hashes -r "$requirements"

[doc("Every check but Nix's")]
[group("Checks")]
checks: lock-check ruff-checks static vulture pytest matrix dprint-check cog audit

[doc("The flake: every system evaluated, this one's checks built")]
[group("Nix")]
nix:
    nix flake check --no-build --all-systems
    nix flake check

[doc("Release a package from main: just release ffmeta minor (major, minor or patch)")]
[group("Misc")]
release package semver:
    #!/usr/bin/env bash
    set -euo pipefail
    # refused before the checks: cog refuses a branch or a dirty tree only after them
    if [ "$(git branch --show-current)" != main ] || [ -n "$(git status --porcelain)" ]; then
        echo "error: a release is cut from main, clean" >&2; exit 1
    fi
    git fetch origin
    if [ "$(git rev-list --count HEAD..origin/main)" -ne 0 ]; then
        echo "error: main is behind origin/main: pull first" >&2; exit 1
    fi
    # cog names the tag, the package and the bump checked: it counts from the package's latest
    # tag, 0.0.0 before its first, so never below the version the package carries
    tag=$(cog bump --package "{{ package }}" --{{ semver }} --dry-run)
    current=$(uv version --package "{{ package }}" --short)
    if ! printf '%s\n' "$current" "${tag#"{{ package }}-v"}" | sort -C -V; then
        echo "error: $tag is below {{ package }} $current" >&2; exit 1
    fi
    just checks
    cog bump --package "{{ package }}" --{{ semver }} --annotated "{{ package }} {{{{version}}"
    # made, the commit and the tag: a failed push is retried as it is, never the bump
    git push --atomic --follow-tags origin main

[doc("git-cliff over a package's commits (cliff.toml); --unreleased: its next section")]
[group("Misc")]
changelog package *args:
    uv run --locked --isolated --only-group release git-cliff --offline --config cliff.toml \
        --include-path "packages/{{ package }}/**" --tag-pattern "^{{ package }}-v" {{ args }}
