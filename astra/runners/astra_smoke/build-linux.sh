#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
workspace_root=$(cd "$script_dir/../../.." && pwd)
source_root="$workspace_root/external/astra"
build_root="$workspace_root/work/astra-linux-build"

if [[ ! -f "$source_root/Cargo.toml" ]]; then
    echo "Astra source checkout not found at $source_root" >&2
    exit 1
fi

docker_arch=$(docker info --format '{{.Architecture}}')
case "$docker_arch" in
    arm64 | aarch64)
        docker_platform=linux/arm64
        ;;
    amd64 | x86_64)
        docker_platform=linux/amd64
        ;;
    *)
        echo "Unsupported Docker architecture: $docker_arch" >&2
        exit 1
        ;;
esac

mkdir -p "$build_root/cargo-home" "$build_root/home" "$build_root/target"

docker run --rm \
    --platform "$docker_platform" \
    --user "$(id -u):$(id -g)" \
    -e HOME=/out/home \
    -e CARGO_HOME=/out/cargo-home \
    -e CARGO_TARGET_DIR=/out/target \
    -v "$source_root:/src:ro" \
    -v "$build_root:/out" \
    -w /src \
    rust:1.97-bookworm \
    cargo build \
        --locked \
        --release \
        --no-default-features \
        --features release-vendored-openssl \
        --manifest-path /src/Cargo.toml \
        -p astra-cli \
        --bin astra

artifact="$build_root/target/release/astra"
if [[ ! -x "$artifact" ]]; then
    echo "Linux Astra artifact was not created at $artifact" >&2
    exit 1
fi

file "$artifact"
shasum -a 256 "$artifact"
docker run --rm \
    --platform "$docker_platform" \
    -v "$artifact:/usr/local/bin/astra:ro" \
    ubuntu:24.04 \
    /usr/local/bin/astra --version

printf 'ASTRA_SMOKE_LINUX_BINARY=%s\n' "$artifact"
