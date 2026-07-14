#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${HOME}/.local/bin"
TARGET_BIN="${TARGET_DIR}/jon-researcher"
TARGET_ALIAS="${TARGET_DIR}/jon"
PATH_MARKER_START="# >>> jon-researcher path >>>"
PATH_MARKER_END="# <<< jon-researcher path <<<"

profile_candidates() {
  printf '%s\n' "${HOME}/.zshrc"
  printf '%s\n' "${HOME}/.bashrc"
  printf '%s\n' "${HOME}/.profile"
}

remove_path_block() {
  local profile="$1"
  local tmp_file
  [[ -f "${profile}" ]] || return 0
  grep -Fq "${PATH_MARKER_START}" "${profile}" || return 0

  tmp_file="$(mktemp)"
  awk -v start="${PATH_MARKER_START}" -v end="${PATH_MARKER_END}" '
    index($0, start) { skip = 1; next }
    index($0, end) { skip = 0; next }
    !skip { print }
  ' "${profile}" > "${tmp_file}"
  mv "${tmp_file}" "${profile}"
  echo "Removed PATH block from ${profile}"
}

if [[ -L "${TARGET_ALIAS}" || -f "${TARGET_ALIAS}" ]]; then
  rm -f "${TARGET_ALIAS}"
  echo "Removed ${TARGET_ALIAS}"
fi

if [[ -f "${TARGET_BIN}" ]]; then
  rm -f "${TARGET_BIN}"
  echo "Removed ${TARGET_BIN}"
fi

while IFS= read -r profile; do
  remove_path_block "${profile}"
done < <(profile_candidates)

echo "Uninstalled jon-researcher."
echo "Restart your shell, or remove ~/.local/bin from PATH for this terminal if needed."
