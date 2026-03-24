#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_SCRIPT="$REPO_ROOT/scripts/run_macro_intel_cron.sh"

BEGIN_TAG="# >>> trading_agent_ultra_macro_intel >>>"
END_TAG="# <<< trading_agent_ultra_macro_intel <<<"

MODE="${1:---install}"

build_block() {
  cat <<EOF
$BEGIN_TAG
CRON_TZ=Asia/Shanghai
0 8,20 * * * $RUN_SCRIPT
$END_TAG
EOF
}

load_current_crontab() {
  crontab -l 2>/dev/null || true
}

strip_block() {
  awk -v begin="$BEGIN_TAG" -v end="$END_TAG" '
    $0 == begin {skip=1; next}
    $0 == end {skip=0; next}
    skip != 1 {print}
  '
}

install_block() {
  local current cleaned tmpfile
  current="$(load_current_crontab)"
  cleaned="$(printf "%s\n" "$current" | strip_block)"

  tmpfile="$(mktemp)"
  {
    printf "%s\n" "$cleaned" | sed '/^[[:space:]]*$/N;/^\n$/D'
    [[ -n "$cleaned" ]] && echo
    build_block
  } >"$tmpfile"

  crontab "$tmpfile"
  rm -f "$tmpfile"

  echo "Installed macro cron schedule (08:00 and 20:00 Asia/Shanghai)."
  echo "Runner: $RUN_SCRIPT"
}

remove_block() {
  local current cleaned tmpfile
  current="$(load_current_crontab)"
  cleaned="$(printf "%s\n" "$current" | strip_block)"

  tmpfile="$(mktemp)"
  printf "%s\n" "$cleaned" >"$tmpfile"
  crontab "$tmpfile"
  rm -f "$tmpfile"

  echo "Removed macro cron schedule block."
}

show_block() {
  echo "Current crontab (macro block highlighted by tags):"
  load_current_crontab
}

case "$MODE" in
--install)
  install_block
  ;;
--remove)
  remove_block
  ;;
--show)
  show_block
  ;;
*)
  echo "Usage: $0 [--install|--remove|--show]"
  exit 1
  ;;
esac
