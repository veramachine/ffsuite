#!/usr/bin/env bash
# git-cliff over one package (cliff.toml): the commits touching packages/PACKAGE, between its own
# tags. The release's bump writes its CHANGELOG.md with it (cog.toml), `just changelog` previews
# the next section; any other arguments are git-cliff's. git-cliff is the lock's (the `release`
# group), offline.
set -euo pipefail

package=${1:?usage: changelog.sh PACKAGE [GIT-CLIFF ARGUMENTS...]}
shift
cd "$(git rev-parse --show-toplevel)"
exec uv run --locked --isolated --only-group release git-cliff --offline --config cliff.toml \
  --include-path "packages/$package/**" --tag-pattern "^$package-v" "$@"
