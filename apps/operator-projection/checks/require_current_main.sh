#!/usr/bin/env bash
# Require this exact package tag to identify the presently fetched main commit.
set -euo pipefail

[[ "$#" -eq 2 ]] || exit 1
release_tag="$1"
expected_sha="$2"
[[ "$release_tag" =~ ^operator-projection-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || exit 1
[[ "${GITHUB_REF:-}" == "refs/tags/$release_tag" ]] || exit 1
git fetch --no-tags origin main
[[ "$(git rev-parse HEAD)" == "$expected_sha" ]] || exit 1
[[ "$(git rev-parse "refs/tags/$release_tag^{commit}")" == "$expected_sha" ]] || exit 1
[[ "$(git rev-parse refs/remotes/origin/main)" == "$expected_sha" ]] || {
  echo "tag does not name current canonical main" >&2
  exit 1
}
