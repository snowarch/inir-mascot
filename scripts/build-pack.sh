#!/usr/bin/env bash
# Build the installable mascot pack: every flat pose/animation, nothing else.
# The tarball extracts directly into the shell's assets/images/mascot dir,
# so it must contain only top-level inir-mascot-*.png / *.gif files.
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
out="${repo_dir}/inir-mascot-pack.tar.gz"

cd "$repo_dir"
shopt -s nullglob
files=(inir-mascot-*.png inir-mascot-*.gif)
if ((${#files[@]} == 0)); then
  echo "error: no assets found in ${repo_dir}" >&2
  exit 1
fi

tar -czf "$out" "${files[@]}"
echo "pack: $out"
echo "assets: ${#files[@]}"
du -h "$out" | cut -f1 | xargs echo "size:"
