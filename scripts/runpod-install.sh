#!/usr/bin/env bash
set -Eeuo pipefail

script_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly script_root
readonly manager="${script_root}/deploy/runpod/runpod_deploy.py"
readonly setup_lock="/run/video-factory-package-install.lock"
readonly min_free_kib=$((8 * 1024 * 1024))
temporary_key=""
created_policy_rc=false

cleanup() {
  if [[ -n "${temporary_key}" && -f "${temporary_key}" ]]; then
    rm -f -- "${temporary_key}"
  fi
  if [[ "${created_policy_rc}" == "true" ]] &&
    grep -q '^# video-factory-temporary-policy$' /usr/sbin/policy-rc.d; then
    rm -f -- /usr/sbin/policy-rc.d
  fi
}
trap cleanup EXIT

usage() {
  cat <<'EOF'
Usage: bash scripts/runpod-install.sh --ref FULL_GIT_SHA --accept-ephemeral \
         (--initialize-empty-database | --restore /absolute/backup.tar.gz) [options]

Prepares supported Ubuntu dependencies, validates Python/Node, and delegates the
transactional application install to runpodctl. The ref must be a full Git SHA.

Options forwarded to the deployment manager:
  --repository URL
  --ref FULL_GIT_SHA
  --accept-ephemeral
  --initialize-empty-database
  --restore ABSOLUTE_ARCHIVE
  --password-file PRIVATE_ABSOLUTE_FILE
  --owner-id OPAQUE_OWNER_ID
  -h, --help
EOF
}

if (($# == 0)); then
  usage
  exit 3
fi
for argument in "$@"; do
  if [[ "${argument}" == "-h" || "${argument}" == "--help" ]]; then
    usage
    exit 0
  fi
done

if [[ "$(id -u)" -ne 0 ]]; then
  printf 'ERROR: run the installer as root inside the RunPod container.\n' >&2
  exit 3
fi
if [[ ! -r /etc/os-release ]]; then
  printf 'ERROR: /etc/os-release is unavailable; only tested Ubuntu containers are supported.\n' >&2
  exit 5
fi
# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
  printf 'ERROR: unsupported OS %s; this installer is tested only on Ubuntu.\n' "${ID:-unknown}" >&2
  exit 5
fi
if [[ "$(uname -m)" != "x86_64" ]]; then
  printf 'ERROR: unsupported architecture %s; expected x86_64.\n' "$(uname -m)" >&2
  exit 5
fi
if [[ ! -f "${manager}" ]]; then
  printf 'ERROR: deployment manager is missing from this checkout.\n' >&2
  exit 3
fi

available_kib="$(df -Pk /opt | awk 'NR == 2 {print $4}')"
if [[ ! "${available_kib}" =~ ^[0-9]+$ ]] || ((available_kib < min_free_kib)); then
  printf 'ERROR: at least 8 GiB free is required under /opt for the demo build.\n' >&2
  exit 5
fi

exec 9>"${setup_lock}"
if ! flock -n 9; then
  printf 'ERROR: another RunPod package installation is active.\n' >&2
  exit 4
fi

base_packages=(
  ca-certificates curl git gnupg iproute2 nginx postgresql postgresql-client
  python3 python3-pip python3-venv supervisor util-linux
)
missing_packages=()
for package in "${base_packages[@]}"; do
  if ! dpkg-query -W -f='${Status}' "${package}" 2>/dev/null | grep -q 'install ok installed'; then
    missing_packages+=("${package}")
  fi
done
if ((${#missing_packages[@]})); then
  if [[ ! -e /usr/sbin/policy-rc.d ]]; then
    printf '%s\n%s\n' '# video-factory-temporary-policy' 'exit 101' >/usr/sbin/policy-rc.d
    chmod 0755 /usr/sbin/policy-rc.d
    created_policy_rc=true
  fi
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing_packages[@]}"
fi

python_requirement="$(sed -n 's/^requires-python = "\([^"]*\)"/\1/p' "${script_root}/pyproject.toml")"
python_version="$(/usr/bin/python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if ! /usr/bin/python3 - "${python_requirement}" <<'PY'
import re
import sys

current = sys.version_info[:2]
clauses = sys.argv[1].split(",")
valid = True
for clause in clauses:
    match = re.fullmatch(r"(>=|<)([0-9]+)\.([0-9]+)", clause.strip())
    if match is None:
        raise SystemExit(2)
    target = (int(match.group(2)), int(match.group(3)))
    valid = valid and (current >= target if match.group(1) == ">=" else current < target)
raise SystemExit(not valid)
PY
then
  printf 'ERROR: repository requires Python %s; found %s.\n' \
    "${python_requirement}" "${python_version}" >&2
  exit 5
fi

node_requirement="$(/usr/bin/python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["engines"]["node"])' "${script_root}/frontend/package.json")"
if [[ ! "${node_requirement}" =~ ^\>=([0-9]+)\.([0-9]+)(\.[0-9]+)?$ ]]; then
  printf 'ERROR: unsupported Node engine expression %s.\n' "${node_requirement}" >&2
  exit 5
fi
node_required_major="${BASH_REMATCH[1]}"
node_required_minor="${BASH_REMATCH[2]}"
node_ok=false
if command -v node >/dev/null 2>&1; then
  node_ok="$(node -e 'const [a,b]=process.versions.node.split(".").map(Number); const [ra,rb]=process.argv.slice(1).map(Number); process.stdout.write(String(a>ra || (a===ra && b>=rb)))' "${node_required_major}" "${node_required_minor}")"
fi
if [[ "${node_ok}" != "true" ]]; then
  readonly nodesource_key_url="https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key"
  readonly nodesource_fingerprint="6F71F525282841EEDAF851B42F59B5F99B1BE0B4"
  temporary_key="$(mktemp)"
  curl --fail --silent --show-error --location "${nodesource_key_url}" --output "${temporary_key}"
  downloaded_fingerprint="$(gpg --show-keys --with-colons "${temporary_key}" | awk -F: '$1 == "fpr" {print $10; exit}')"
  if [[ "${downloaded_fingerprint}" != "${nodesource_fingerprint}" ]]; then
    printf 'ERROR: NodeSource signing-key fingerprint did not match the pinned fingerprint.\n' >&2
    exit 5
  fi
  gpg --dearmor --yes --output /usr/share/keyrings/nodesource.gpg "${temporary_key}"
  chmod 0644 /usr/share/keyrings/nodesource.gpg
  printf 'deb [arch=amd64 signed-by=/usr/share/keyrings/nodesource.gpg] https://deb.nodesource.com/node_%s.x nodistro main\n' "${node_required_major}" \
    >/etc/apt/sources.list.d/nodesource.list
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends nodejs
fi

if ! command -v tailscale >/dev/null 2>&1 || ! command -v tailscaled >/dev/null 2>&1; then
  codename="${VERSION_CODENAME:-}"
  if [[ -z "${codename}" ]]; then
    printf 'ERROR: Ubuntu VERSION_CODENAME is unavailable for the Tailscale repository.\n' >&2
    exit 5
  fi
  curl --fail --silent --show-error --location \
    "https://pkgs.tailscale.com/stable/ubuntu/${codename}.noarmor.gpg" \
    --output /usr/share/keyrings/tailscale-archive-keyring.gpg
  chmod 0644 /usr/share/keyrings/tailscale-archive-keyring.gpg
  curl --fail --silent --show-error --location \
    "https://pkgs.tailscale.com/stable/ubuntu/${codename}.tailscale-keyring.list" \
    --output /etc/apt/sources.list.d/tailscale.list
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tailscale
fi

node_version="$(node --version)"
if ! node -e 'const [a,b]=process.versions.node.split(".").map(Number); const [ra,rb]=process.argv.slice(1).map(Number); process.exit(a>ra || (a===ra && b>=rb) ? 0 : 1)' "${node_required_major}" "${node_required_minor}"; then
  printf 'ERROR: frontend requires Node %s; found %s.\n' "${node_requirement}" "${node_version}" >&2
  exit 5
fi

install -m 0755 "${script_root}/scripts/runpodctl" /usr/local/bin/runpodctl
printf 'Validated Ubuntu %s, Python %s, Node %s.\n' "${VERSION_ID:-unknown}" "${python_version}" "${node_version}"
/usr/bin/python3 "${manager}" install "$@"
