#!/usr/bin/env bash
# A package's tag (ffmeta-v0.2.0) read as the package it releases: the name printed once the tag's
# version is the one that package's pyproject.toml declares. release.yml's and publish.yml's.
set -euo pipefail

tag=${1:?usage: package-tag.sh TAG (e.g. ffmeta-v0.2.0)}
package=${tag%-v*}
version=${tag##*-v}
declared=$(uv version --package "$package" --short)
if [[ $version != "$declared" ]]; then
  echo "$tag: $package's pyproject.toml declares $declared" >&2
  exit 1
fi
echo "$package"
