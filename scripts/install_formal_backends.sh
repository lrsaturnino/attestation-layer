#!/usr/bin/env bash
#
# install_formal_backends.sh — fetch and checksum-verify the pinned formal backends.
#
# The S ∧ R consistency check (PB-1) and the bounded backends run external model
# checkers, not Python dependencies. This script pins exact versions and verifies each
# download against a published SHA-256 before installing, so a run records a known-good,
# reproducible tool. A checksum mismatch aborts the install — a tampered or wrong artifact
# never reaches the trusted computing base.
#
# Backends (see docs/formal-backend-guide.md):
#   - Apalache (apalache-mc)  — PRIMARY symbolic model checker for S ∧ R.
#   - TLC (tla2tools.jar)     — RESERVE explicit-state checker.
#
# Usage:
#   scripts/install_formal_backends.sh [--prefix DIR] [--apalache-only] [--tlc-only]
#
# Default prefix is ${HOME}/.local. Apalache is unpacked to <prefix>/opt/apalache and a
# launcher symlinked into <prefix>/bin; tla2tools.jar is placed in <prefix>/lib. Add
# <prefix>/bin to PATH so `apalache-mc` resolves.
#
set -euo pipefail

# --- Pinned versions and published SHA-256 checksums -------------------------------------
# Apalache 0.58.0: checksum cross-verified against the release's official sha256sum.txt and
# the GitHub release-asset digest (both: 55b4da12…b9b3d7 for apalache-0.58.0.tgz).
APALACHE_VERSION="0.58.0"
APALACHE_URL="https://github.com/apalache-mc/apalache/releases/download/v${APALACHE_VERSION}/apalache-${APALACHE_VERSION}.tgz"
APALACHE_SHA256="55b4da129140b3b6b4106b31eddf36b5f49d896bf2ec8b4cf81c93bc37b9b3d7"

# TLC (tla2tools) 1.7.4: checksum computed from the official release jar.
TLC_VERSION="1.7.4"
TLC_URL="https://github.com/tlaplus/tlaplus/releases/download/v${TLC_VERSION}/tla2tools.jar"
TLC_SHA256="936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88"

PREFIX="${HOME}/.local"
INSTALL_APALACHE=1
INSTALL_TLC=1

while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="$2"; shift 2 ;;
    --apalache-only) INSTALL_TLC=0; shift ;;
    --tlc-only) INSTALL_APALACHE=0; shift ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# --- Portable SHA-256 verification --------------------------------------------------------
sha256_of() {
  # Print the lowercase hex SHA-256 of the file in $1, using whichever tool exists.
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    echo "error: neither sha256sum nor shasum is available" >&2
    exit 3
  fi
}

verify_or_die() {
  # verify_or_die <file> <expected_sha256> <label>
  local file="$1" expected="$2" label="$3" actual
  actual="$(sha256_of "$file")"
  if [ "$actual" != "$expected" ]; then
    echo "CHECKSUM MISMATCH for ${label}:" >&2
    echo "  expected: ${expected}" >&2
    echo "  actual:   ${actual}" >&2
    echo "Refusing to install a non-matching artifact." >&2
    rm -f "$file"
    exit 4
  fi
  echo "  checksum OK (${label}): ${actual}"
}

download() {
  # download <url> <dest>
  local url="$1" dest="$2"
  echo "  downloading ${url}"
  if command -v curl >/dev/null 2>&1; then
    curl -fSL --retry 3 -o "$dest" "$url"
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O "$dest" "$url"
  else
    echo "error: neither curl nor wget is available" >&2
    exit 3
  fi
}

mkdir -p "${PREFIX}/bin" "${PREFIX}/lib" "${PREFIX}/opt"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "${WORKDIR}"' EXIT

if [ "${INSTALL_APALACHE}" -eq 1 ]; then
  echo "Installing Apalache ${APALACHE_VERSION} (primary)…"
  download "${APALACHE_URL}" "${WORKDIR}/apalache.tgz"
  verify_or_die "${WORKDIR}/apalache.tgz" "${APALACHE_SHA256}" "apalache-${APALACHE_VERSION}.tgz"
  # The tarball unpacks to a *versioned* top-level directory `apalache-<version>/` whose
  # bin/apalache-mc launcher runs `java -jar lib/apalache.jar`, so the symlink must target the
  # versioned path (an unversioned `apalache/` does not exist and would dangle). Apalache needs
  # a JDK 17+ `java` on PATH.
  rm -rf "${PREFIX}/opt/apalache-${APALACHE_VERSION}"
  tar -xzf "${WORKDIR}/apalache.tgz" -C "${PREFIX}/opt"
  ln -sf "${PREFIX}/opt/apalache-${APALACHE_VERSION}/bin/apalache-mc" "${PREFIX}/bin/apalache-mc"
  echo "  installed: ${PREFIX}/bin/apalache-mc"
  "${PREFIX}/bin/apalache-mc" version || true
fi

if [ "${INSTALL_TLC}" -eq 1 ]; then
  echo "Installing TLC / tla2tools ${TLC_VERSION} (reserve)…"
  download "${TLC_URL}" "${WORKDIR}/tla2tools.jar"
  verify_or_die "${WORKDIR}/tla2tools.jar" "${TLC_SHA256}" "tla2tools-${TLC_VERSION}.jar"
  cp "${WORKDIR}/tla2tools.jar" "${PREFIX}/lib/tla2tools.jar"
  echo "  installed: ${PREFIX}/lib/tla2tools.jar"
  echo "  run TLC with: java -cp ${PREFIX}/lib/tla2tools.jar tlc2.TLC <module>"
fi

echo "Done. Ensure ${PREFIX}/bin is on PATH so apalache-mc resolves."
