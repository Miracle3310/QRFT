# QRFT

QRFT means **Quick Raster File Transfer**. It transfers small files through a
screen capture path: the source side shows large black/white raster frames, and
the receiver side captures screenshots, decodes frames, verifies CRCs, and
reconstructs the original file.

The project is designed for simple, local, authorized file movement where a
visual channel is available but normal file transfer is inconvenient.

## Requirements

Source side:

- Python 3.8 or newer.
- Python standard library only.
- `tkinter` with working GUI display support.

Receiver side:

- Python 3.8 or newer.
- `numpy`
- `opencv-python`
- `requests` for URL snapshot mode.

Install receiver dependencies:

```bash
python -m pip install numpy opencv-python requests
```

## Files

- `qrft_send.py`: short stdlib-only sender for keyboard-paste transfer.
- `qrft_recv.py`: OpenCV/numpy screenshot decoder.
- `qrft_protocol.md`: frame format.
- `check_python_env.py`: stdlib-only environment probe.

## Sender

Copy the short sender to the source machine, then run:

```powershell
python qrft_send.py test.txt
```

Press `Enter`, `Space`, `Right`, or `n` on the source machine to advance one
frame. Press `Left`, `Backspace`, or `p` to go back one frame. Press `Escape` to
exit fullscreen playback.

The sender uses a `260 x 120` data grid and lifts the frame upward before
choosing the cell size. On 1920 x 1080 captures this usually means 7 px cells
and about 3740 payload bytes per frame, while avoiding bottom letterbox bars
clipping the lower data rows.

## Receiver

Decode screenshots already saved in a folder:

```bash
python qrft_recv.py --folder snapshot --out decoded_test.txt
```

For new sender frames, the output filename comes from the transmitted basename.
`--out` is used as the destination directory anchor. For example,
`--out output/placeholder.bin` writes the recovered original filename under
`output/`. Old frames without filename metadata still write exactly to `--out`.

For URL capture, the decoder clears old screenshots before starting by default:

```bash
python qrft_recv.py --url "https://your-kvm-host/api/streamer/snapshot?save=1&preview_quality=95" --folder snapshot --out out/received.bin --interval 0.5 --insecure
```

Add `--keep-folder` only when you intentionally want to mix existing screenshots
with new captures.

For self-signed HTTPS endpoints, add `--insecure`. If the capture endpoint is
not compatible with this URL mode, keep using folder mode.

For deterministic multi-frame capture, run the sender in its default key-step
mode and let the receiver request missing frames through the keyboard endpoint:

```bash
python qrft_recv.py --url "https://your-kvm-host/api/streamer/snapshot?save=1&preview_quality=95" --advance-key Enter --targeted --folder snapshot --out out/received.bin --insecure
```

In targeted mode, the receiver types a frame number followed by `Enter` to make
the sender jump directly to a missing frame. This avoids relying on fixed timing
or repeatedly cycling through all frames.

`--advance-key` derives a KVM-style `send_key` URL from the snapshot URL for
simple next-frame mode. If the keyboard endpoint is different, pass a template
explicitly:

```bash
python qrft_recv.py --url "https://your-kvm-host/api/streamer/snapshot?save=1&preview_quality=95" --key-url-template "https://your-kvm-host/api/hid/events/send_key?key={key}&finish=1" --targeted --folder snapshot --out out/received.bin --insecure
```

For targeted mode, number keys are sent as `Digit0` through `Digit9`, matching
common KVM keyboard event naming.

Add `--profile` to print snapshot, decode, and key/settle timing.
