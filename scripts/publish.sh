#!/usr/bin/env bash
# Create the GitHub repository from this local checkout, then push.
#
#   ./scripts/publish.sh                 # public repo in your account
#   ./scripts/publish.sh --private
#
# Requires the GitHub CLI (https://cli.github.com) and an authenticated session
# (`gh auth login`). Edit OWNER below to publish under an organisation.
set -euo pipefail

OWNER=""                     # empty = your personal account
NAME="pvp-team-builder"
DESCRIPTION="Team search for Pokemon GO PvP, scored with PvPoke's own battle engine"
VISIBILITY="--public"

for arg in "$@"; do
  case "$arg" in
    --private) VISIBILITY="--private" ;;
    --public)  VISIBILITY="--public" ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

target="${NAME}"
[ -n "$OWNER" ] && target="${OWNER}/${NAME}"

gh repo create "$target" "$VISIBILITY" \
  --description "$DESCRIPTION" \
  --source . --remote origin --push

gh repo edit "$target" \
  --add-topic pokemon-go \
  --add-topic pogo \
  --add-topic pvp \
  --add-topic gbl \
  --add-topic pvpoke \
  --add-topic team-builder \
  --add-topic python \
  --add-topic simulator

echo "published: https://github.com/${target}"
