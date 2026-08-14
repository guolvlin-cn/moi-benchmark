#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cache_root="${PI_TBENCH_VERIFIER_CACHE:-}"
cache_proxy="${PI_TBENCH_CACHE_PROXY_URL:-}"
uv_version="0.9.5"
uv_target="uv-x86_64-unknown-linux-gnu"
python_release="20251014"

usage() {
  cat <<'EOF'
Prepare the Linux/amd64 verifier bootstrap cache.

Usage: prepare-verifier-cache.sh --cache-root DIR

PI_TBENCH_CACHE_PROXY_URL may name an HTTP proxy used only for host downloads.
EOF
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --cache-root) cache_root="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -n "${cache_root}" ]] || { usage >&2; exit 2; }
mkdir -p \
  "${cache_root}/bin" \
  "${cache_root}/downloads" \
  "${cache_root}/python-build-standalone/${python_release}"

curl_args=(
  --fail
  --location
  --show-error
  --silent
  --retry 10
  --retry-delay 2
  --retry-all-errors
)
if [[ -n "${cache_proxy}" ]]; then
  curl_args+=(--proxy "${cache_proxy}")
fi

download() {
  local url="$1"
  local destination="$2"
  local partial="${destination}.part"
  if [[ -f "${destination}" ]] && tar -tzf "${destination}" >/dev/null 2>&1; then
    return 0
  fi
  echo "Caching $(basename "${destination}")"
  # Do not resume a partial GitHub release download: some local proxies have
  # returned an invalid Range response that produces a corrupt concatenation.
  curl "${curl_args[@]}" --output "${partial}" "${url}"
  tar -tzf "${partial}" >/dev/null
  mv "${partial}" "${destination}"
}

uv_archive="${cache_root}/downloads/${uv_target}.tar.gz"
download \
  "https://github.com/astral-sh/uv/releases/download/${uv_version}/${uv_target}.tar.gz" \
  "${uv_archive}"
tar -tzf "${uv_archive}" >/dev/null

tar -xzf "${uv_archive}" \
  -C "${cache_root}/bin" \
  --strip-components=1 \
  "${uv_target}/uv" \
  "${uv_target}/uvx"
chmod 0755 "${cache_root}/bin/uv" "${cache_root}/bin/uvx"
install -m 0755 "${script_dir}/cached-curl.sh" "${cache_root}/bin/curl"

python_assets=(
  "cpython-3.11.14+20251014-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
  "cpython-3.12.12+20251014-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
  "cpython-3.13.9+20251014-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
)
for asset in "${python_assets[@]}"; do
  target="${cache_root}/python-build-standalone/${python_release}/${asset}"
  encoded_asset="${asset/+/%2B}"
  download \
    "https://github.com/astral-sh/python-build-standalone/releases/download/${python_release}/${encoded_asset}" \
    "${target}"
  tar -tzf "${target}" >/dev/null
done

echo "Verifier bootstrap cache ready: ${cache_root}"
