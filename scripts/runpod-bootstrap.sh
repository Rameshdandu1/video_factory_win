#!/usr/bin/env bash
set -Eeuo pipefail

readonly repository="https://github.com/Rameshdandu1/video_factory_win.git"

usage() {
  cat <<'EOF'
Usage: bash runpod-bootstrap.sh --ref FULL_GIT_SHA --accept-ephemeral \
         (--initialize-empty-database | --restore /absolute/backup.tar.gz) [install options]

Fetches exactly the approved Git object into a temporary checkout, verifies the
resolved object ID, and invokes the versioned RunPod installer. It does not edit
the template entrypoint, ComfyUI, JupyterLab, or RunPod resource settings.
EOF
}

revision=""
arguments=("$@")
for ((index = 0; index < $#; index++)); do
  argument="${arguments[index]}"
  if [[ "${argument}" == "-h" || "${argument}" == "--help" ]]; then
    usage
    exit 0
  fi
  if [[ "${argument}" == "--ref" && $((index + 1)) -lt $# ]]; then
    revision="${arguments[index + 1]}"
  fi
done
if [[ ! "${revision}" =~ ^[0-9a-f]{40}$ ]]; then
  printf 'ERROR: --ref must be a full lowercase 40-character Git SHA.\n' >&2
  exit 3
fi
if [[ "$(id -u)" -ne 0 ]]; then
  printf 'ERROR: run the bootstrap as root inside the RunPod container.\n' >&2
  exit 3
fi

checkout="$(mktemp -d -t video-factory-bootstrap.XXXXXXXX)"
cleanup() {
  local resolved_tmp resolved_checkout
  resolved_tmp="$(realpath -- "${TMPDIR:-/tmp}")"
  resolved_checkout="$(realpath -- "${checkout}")"
  case "${resolved_checkout}" in
    ("${resolved_tmp}"/video-factory-bootstrap.*) rm -rf --one-file-system -- "${resolved_checkout}" ;;
    (*) printf 'ERROR: refusing to remove unexpected bootstrap path %s.\n' "${resolved_checkout}" >&2 ;;
  esac
}
trap cleanup EXIT
git init --quiet "${checkout}"
git -C "${checkout}" remote add origin "${repository}"
git -C "${checkout}" fetch --quiet --depth=1 origin "${revision}"
resolved="$(git -C "${checkout}" rev-parse FETCH_HEAD)"
if [[ "${resolved}" != "${revision}" ]]; then
  printf 'ERROR: fetched Git object does not match the approved ref.\n' >&2
  exit 4
fi
git -C "${checkout}" checkout --quiet --detach FETCH_HEAD
/usr/bin/env bash "${checkout}/scripts/runpod-install.sh" "$@"
