# QRFT Python protocol notes

This project uses a deliberately simple black/white cell protocol.

- Encoder side: Python 3.8 stdlib only, intended for the source machine.
- Decoder side: Python with `opencv-python` and `numpy`, intended for the receiver machine.
- Logical data grid: `260 x 120` bits.
- Margin: `6` cells on every side, so the rendered frame is `272 x 132` cells.
- On a 1920 x 1080 screen this normally renders with 7 px cells.
- Header size: 32 bytes.
- Header repeats: 5.
- Payload capacity: `260 * 120 / 8 - 32 * 5 = 3740` bytes per frame.

The sender displays one frame at a time. Keyboard input advances the frame, so a
receiver that can send keys through the capture device can deterministically
capture every frame instead of relying on timing.

Header, big endian:

```text
4s  magic      b"QF10"
B   version    1
B   header_len 32
H   frame_idx  zero-based
H   total
I   file_size
H   payload_len
I   file_crc32
I   frame_crc32 over payload bytes
8s  reserved
```

The decoder majority-votes the five header copies, verifies each frame CRC,
deduplicates repeated frames, reports missing frame indexes, and writes the
output only when all frames are present and the final file CRC matches.

The transmitted byte stream is a named payload:

```text
H     filename_len
bytes UTF-8 basename
bytes original file content
```

`file_size` and `file_crc32` in the header refer to this complete named payload.
After CRC verification the decoder strips the filename envelope and writes the
original file content using the transmitted basename. If the envelope is absent
or invalid, the decoder falls back to the path provided by `--out`.
