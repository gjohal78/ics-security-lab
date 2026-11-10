#!/usr/bin/env bash
# Thin wrapper around run_experiments.py — resets the lab in each topology,
# runs every attack flat and zoned, and writes docs/results.md.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 run_experiments.py "$@"
