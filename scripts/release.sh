#!/usr/bin/env bash
# Cut a mascot pack release in one command:
#
#   scripts/release.sh v2 "Added 6 new chaos poses"
#
# Refuses to run on a dirty tree, builds the pack, tags, pushes and
# publishes the GitHub release. iNiR installs and updates download from
# releases/latest, so publishing here is the whole delivery.
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
tag="${1:?usage: release.sh <tag> [notes], e.g. release.sh v2 \"new poses\"}"
notes="${2:-Mascot pack ${tag}}"

cd "$repo_dir"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "error: uncommitted changes. Run sync-from-shell.sh, review, commit, then release." >&2
  exit 1
fi
if git rev-parse "$tag" >/dev/null 2>&1; then
  echo "error: tag ${tag} already exists" >&2
  exit 1
fi

./scripts/build-pack.sh
git tag "$tag"
git push origin main "$tag"
gh release create "$tag" inir-mascot-pack.tar.gz --title "Mascot pack ${tag}" --notes "$notes"
echo "released ${tag}. Installs and updates pick it up automatically."
echo "reminder: add a ${tag} entry to CHANGELOG.md."
