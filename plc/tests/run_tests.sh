#!/usr/bin/env bash
# Compile tank_control.st with matiec (the ST compiler OpenPLC uses), then
# run harness.c, which drives the generated code scan-by-scan through the
# control scenarios. Needs: git, gcc, g++, make, autoconf, automake, flex, bison.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${HERE}/.build"
MATIEC="${WORK}/OpenPLC_v3/utils/matiec_src"

mkdir -p "$WORK"

# Build matiec once from the same OpenPLC_v3 repo the container uses.
if [[ ! -x "${MATIEC}/iec2c" ]]; then
  echo "Building matiec (first run only)..."
  git clone --depth 1 -q https://github.com/thiagoralves/OpenPLC_v3.git "${WORK}/OpenPLC_v3"
  (cd "$MATIEC" && autoreconf -i >/dev/null 2>&1 && ./configure >/dev/null && make -j"$(nproc)" >/dev/null)
fi

# Same iec2c flags as OpenPLC's compile_program.sh.
OUT="${WORK}/gen"
rm -rf "$OUT" && mkdir -p "$OUT"
"${MATIEC}/iec2c" -I "${MATIEC}/lib" -T "$OUT" -f -l -p -r -R -a "${HERE}/../tank_control.st"

gcc -w -I "$OUT" -I "${MATIEC}/lib/C" "${HERE}/harness.c" "$OUT/Config0.c" "$OUT/Res0.c" -o "${WORK}/harness"
"${WORK}/harness"
