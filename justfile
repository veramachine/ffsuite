# csan's Justfile for the workspace, its groups and aliases, with imi's `checks`, `cog`,
# `dprint-check`, `audit` and `release`. The commands are the workflows' (.github/workflows/):
# `just checks` runs checks.yml's -- in the dev shell with every test, ffmpeg's and the matrix --
# the style checks', security.yml's and, last, nix.yml's (`just nix`). Run them in `nix develop`.

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

# `nix` last: the slowest, and the one a machine without Nix cannot run -- every other has passed
# by then. The flake sees git's files only: a new file is invisible to it until `git add`ed.
[doc("Every check, the flake's last")]
[group("Checks")]
checks: lock-check ruff-checks static vulture pytest matrix dprint-check cog audit nix

[doc("The flake: every system evaluated, this one's checks built")]
[group("Nix")]
nix:
    nix flake check --no-build --all-systems
    nix flake check

[doc("Every package's sdist and wheel into dist/, as publish.yml builds them (--no-sources)")]
[group("Misc")]
build:
    uv build --all-packages --no-sources

[doc("Release a package from main: just release ffmeta minor (major, minor or patch)")]
[group("Misc")]
release package semver:
    #!/usr/bin/env bash
    set -euo pipefail
    package="{{ package }}"
    # refused before the checks: cog refuses a branch or a dirty tree only after them
    if [ "$(git branch --show-current)" != main ] || [ -n "$(git status --porcelain)" ]; then
        echo "error: a release is cut from main, clean" >&2; exit 1
    fi
    git fetch --tags origin
    if [ "$(git rev-list --count HEAD..origin/main)" -ne 0 ]; then
        echo "error: main is behind origin/main: pull first" >&2; exit 1
    fi
    # cog counts from the package's latest tag (0.0.0 before its first), so the version the
    # package carries is tagged on origin -- each 0.1.0, published by hand, too (CONTRIBUTING.md)
    current=$(uv version --package "$package" --short)
    if ! git ls-remote --exit-code --tags origin "refs/tags/$package-v$current" >/dev/null; then
        echo "error: $package-v$current is not on origin: tag it and push it first" >&2; exit 1
    fi
    tag=$(cog bump --package "$package" --{{ semver }} --dry-run)
    next=${tag#"$package-v"}
    if [ "$next" = "$current" ] || ! printf '%s\n' "$current" "$next" | sort -C -V; then
        echo "error: $tag is not above $package $current" >&2; exit 1
    fi
    if [ "$package" = ffman ]; then
        # its wheel requires its libraries: each released as the workspace holds it, ffman's floor
        # that release's minor -- else pip may pair it with one lacking what it imports
        uv run --locked python - <<'EOF'
    import subprocess
    import sys
    import tomllib
    from pathlib import Path

    from packaging.requirements import Requirement
    from packaging.version import Version


    def project(name):
        text = Path(f"packages/{name}/pyproject.toml").read_text(encoding="utf-8")
        return tomllib.loads(text)["project"]


    errors = []
    for req in map(Requirement, project("ffman")["dependencies"]):
        version = Version(project(req.name)["version"])
        tag, src = f"{req.name}-v{version}", f"packages/{req.name}/src"
        diff = ["git", "diff", "--quiet", tag, "HEAD", "--", src]
        if subprocess.run(diff, check=False).returncode:  # 1: changed; 128: no such tag
            errors.append(f"{src} is not {tag}'s: release {req.name} first")
        floor = Version(f"{version.major}.{version.minor}")
        if not any(s.operator == ">=" and Version(s.version) >= floor for s in req.specifier):
            errors.append(f"ffman requires {req}: raise its floor to {floor}")
    sys.exit("\n".join(f"error: {e}" for e in errors) or None)
    EOF
    fi
    just checks
    cog bump --package "$package" --{{ semver }} --annotated "$package {{{{version}}"
    # made, the commit and the tag, pushed together -- that tag alone: --follow-tags would take any
    # other local one too, and more than three at once start no workflow (GitHub's push event). A
    # failed push is retried as it is, never the bump -- unless origin moved meanwhile (refused,
    # not a fast-forward): then drop the tag and the bump's commit, pull, and release again
    git push --atomic origin main "refs/tags/$tag"

[doc("git-cliff over a package's commits (cliff.toml); --unreleased: its next section")]
[group("Misc")]
changelog package *args:
    uv run --locked --isolated --only-group release git-cliff --offline --config cliff.toml \
        --include-path "packages/{{ package }}/**" --tag-pattern "^{{ package }}-v" {{ args }}
