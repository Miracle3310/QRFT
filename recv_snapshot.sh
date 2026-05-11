#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Set SNAPSHOT_URL in your shell; do not commit private KVM hostnames or IPs.
: "${SNAPSHOT_URL:?set SNAPSHOT_URL, for example https://your-kvm-host/api/streamer/snapshot?save=1&preview_quality=80}"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-snapshot}"
OUTPUT_ANCHOR="${OUTPUT_ANCHOR:-out/received.bin}"
PARK_MOUSE="${PARK_MOUSE:-1}"
PARK_MOUSE_DX="${PARK_MOUSE_DX:-32767}"
PARK_MOUSE_DY="${PARK_MOUSE_DY:--32768}"
PARK_MOUSE_STEPS="${PARK_MOUSE_STEPS:-3}"

python3 ensure_receiver_deps.py

PARK_MOUSE_ARGS=()
if [[ "$PARK_MOUSE" != "0" ]]; then
  PARK_MOUSE_ARGS=(--park-mouse-relative --park-mouse-dx "$PARK_MOUSE_DX" --park-mouse-dy "$PARK_MOUSE_DY" --park-mouse-steps "$PARK_MOUSE_STEPS")
fi

exec .venv/bin/python qrft_recv.py \
  --url "$SNAPSHOT_URL" \
  --advance-key Enter \
  --targeted \
  --folder "$SNAPSHOT_DIR" \
  --out "$OUTPUT_ANCHOR" \
  "${PARK_MOUSE_ARGS[@]}" \
  --advance-settle 1.0 \
  --poll-delay 0.3 \
  --target-timeout 6 \
  --profile \
  --insecure \
  "$@"
