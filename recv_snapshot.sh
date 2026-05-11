#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Set SNAPSHOT_URL in your shell; do not commit private KVM hostnames or IPs.
: "${SNAPSHOT_URL:?set SNAPSHOT_URL, for example https://your-kvm-host/api/streamer/snapshot?save=1&preview_quality=80}"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-snapshot}"
OUTPUT_ANCHOR="${OUTPUT_ANCHOR:-out/received.bin}"

python3 ensure_receiver_deps.py

exec .venv/bin/python qrft_recv.py \
  --url "$SNAPSHOT_URL" \
  --advance-key Enter \
  --targeted \
  --folder "$SNAPSHOT_DIR" \
  --out "$OUTPUT_ANCHOR" \
  --advance-settle 0.35 \
  --poll-delay 0.15 \
  --target-timeout 3 \
  --profile \
  --insecure \
  "$@"
