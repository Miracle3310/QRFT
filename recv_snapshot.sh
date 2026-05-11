#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Set SNAPSHOT_URL in your shell; do not commit private KVM hostnames or IPs.
: "${SNAPSHOT_URL:?set SNAPSHOT_URL, for example https://your-kvm-host/api/streamer/snapshot?save=1&preview_quality=80}"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-snapshot}"
OUTPUT_ANCHOR="${OUTPUT_ANCHOR:-out/received.bin}"
KEY_URL_TEMPLATE="${KEY_URL_TEMPLATE:-}"
PARK_MOUSE="${PARK_MOUSE:-1}"
PARK_MOUSE_DX="${PARK_MOUSE_DX:-32767}"
PARK_MOUSE_DY="${PARK_MOUSE_DY:--32768}"
PARK_MOUSE_STEPS="${PARK_MOUSE_STEPS:-3}"
SCAN_CAPTURES="${SCAN_CAPTURES:-0}"
ADAPTIVE_SETTLE="${ADAPTIVE_SETTLE:-1}"

python3 ensure_receiver_deps.py

PARK_MOUSE_ARGS=()
if [[ "$PARK_MOUSE" != "0" ]]; then
  PARK_MOUSE_ARGS=(--park-mouse-relative --park-mouse-dx "$PARK_MOUSE_DX" --park-mouse-dy "$PARK_MOUSE_DY" --park-mouse-steps "$PARK_MOUSE_STEPS")
fi

SCAN_ARGS=()
if [[ "$SCAN_CAPTURES" != "0" ]]; then
  SCAN_ARGS=(--scan-captures "$SCAN_CAPTURES")
fi

ADAPTIVE_ARGS=()
if [[ "$ADAPTIVE_SETTLE" != "0" ]]; then
  ADAPTIVE_ARGS=(--adaptive-settle)
fi

KEY_URL_ARGS=()
if [[ -n "$KEY_URL_TEMPLATE" ]]; then
  KEY_URL_ARGS=(--key-url-template "$KEY_URL_TEMPLATE")
fi

exec .venv/bin/python qrft_recv.py \
  --url "$SNAPSHOT_URL" \
  --advance-key Enter \
  "${KEY_URL_ARGS[@]}" \
  --targeted \
  --folder "$SNAPSHOT_DIR" \
  --out "$OUTPUT_ANCHOR" \
  "${PARK_MOUSE_ARGS[@]}" \
  "${SCAN_ARGS[@]}" \
  "${ADAPTIVE_ARGS[@]}" \
  --advance-settle 1.0 \
  --poll-delay 0.3 \
  --target-timeout 6 \
  --profile \
  --insecure \
  "$@"
