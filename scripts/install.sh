#!/usr/bin/env bash
set -euo pipefail

APP_NAME="jon-researcher"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
SOURCE_BIN="${PROJECT_DIR}/dist/${APP_NAME}"
TARGET_DIR="${HOME}/.local/bin"
TARGET_BIN="${TARGET_DIR}/${APP_NAME}"
TARGET_ALIAS="${TARGET_DIR}/jon"
PATH_MARKER_START="# >>> jon-researcher path >>>"
PATH_MARKER_END="# <<< jon-researcher path <<<"
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'

build_binary() {
  if [[ -x "${SOURCE_BIN}" ]]; then
    return
  fi

  if [[ -x "${PROJECT_DIR}/.venv/bin/pyinstaller" ]]; then
    (cd "${PROJECT_DIR}" && .venv/bin/pyinstaller --clean jon.spec)
    return
  fi

  if command -v pyinstaller >/dev/null 2>&1; then
    (cd "${PROJECT_DIR}" && pyinstaller --clean jon.spec)
    return
  fi

  echo "Could not find ${SOURCE_BIN} and PyInstaller is not available." >&2
  echo "Build first with: cd ${PROJECT_DIR} && pyinstaller --clean jon.spec" >&2
  exit 1
}

profile_candidates() {
  case "$(basename "${SHELL:-}")" in
    zsh)
      printf '%s\n' "${HOME}/.zshrc"
      ;;
    bash)
      printf '%s\n' "${HOME}/.bashrc"
      ;;
    *)
      printf '%s\n' "${HOME}/.profile"
      ;;
  esac
}

ensure_path_block() {
  local profile="$1"
  mkdir -p "$(dirname "${profile}")"
  touch "${profile}"
  if grep -Fq "${PATH_MARKER_START}" "${profile}"; then
    return
  fi
  {
    printf '\n%s\n' "${PATH_MARKER_START}"
    printf '%s\n' "${PATH_LINE}"
    printf '%s\n' "${PATH_MARKER_END}"
  } >> "${profile}"
  echo "Updated PATH in ${profile}"
}

build_binary
mkdir -p "${TARGET_DIR}"
install -m 755 "${SOURCE_BIN}" "${TARGET_BIN}"
ln -sf "${TARGET_BIN}" "${TARGET_ALIAS}"

while IFS= read -r profile; do
  ensure_path_block "${profile}"
done < <(profile_candidates)

echo "Installed ${APP_NAME} to ${TARGET_BIN}"
echo "Installed jon alias to ${TARGET_ALIAS}"
echo "For this terminal session, run:"
echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
echo "Then try:"
echo "  jon-researcher --help"
