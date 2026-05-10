#!/usr/bin/env python3
"""Stdlib-only fullscreen QRFT sender.

Usage on the source machine:

    python qrft_send.py test.txt

Optional arguments:

    python qrft_send.py test.txt 0.8 0

The second argument is seconds per frame. The third is loop count; 0 means
forever. Press Escape to exit.
"""

import os
import struct
import sys
import tkinter as tk
import zlib

W, H, M = 260, 120, 6
HDR, REP = 32, 5
MAGIC, VER = b"QF10", 1
CAP = W * H // 8 - HDR * REP


def bits_from_bytes(data, nbits):
    out = []
    for b in data:
        for k in range(7, -1, -1):
            out.append((b >> k) & 1)
    if len(out) < nbits:
        out += [0] * (nbits - len(out))
    return out[:nbits]


def make_frames(path):
    with open(path, "rb") as f:
        file_data = f.read()
    name = os.path.basename(path).encode("utf-8")
    if len(name) > 255:
        raise SystemExit("file name is too long after UTF-8 encoding")
    data = struct.pack(">H", len(name)) + name + file_data
    fcrc = zlib.crc32(data) & 0xFFFFFFFF
    total = max(1, (len(data) + CAP - 1) // CAP)
    frames = []
    for i in range(total):
        payload = data[i * CAP : (i + 1) * CAP]
        h = struct.pack(
            ">4sBBHHIHII8s",
            MAGIC,
            VER,
            HDR,
            i,
            total,
            len(data),
            len(payload),
            fcrc,
            zlib.crc32(payload) & 0xFFFFFFFF,
            b"\0" * 8,
        )
        bits = bits_from_bytes(h * REP + payload, W * H)
        frames.append(bits)
    return file_data, frames


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "test.txt"
    delay = float(sys.argv[2]) if len(sys.argv) > 2 else 0.8
    loops = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    data, frames = make_frames(path)

    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.configure(bg="white")
    root.bind("<Escape>", lambda _e: root.destroy())

    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    tw, th = W + 2 * M, H + 2 * M
    safe_h = max(1, sh - 120)
    cell = max(1, min(sw // tw, safe_h // th))
    ox = (sw - tw * cell) // 2
    oy = max(8, (sh - th * cell) // 2 - 36)
    c = tk.Canvas(root, width=sw, height=sh, bg="white", highlightthickness=0)
    c.pack()
    state = {"i": 0, "loop": 0}

    def rect(x, y):
        c.create_rectangle(
            ox + x * cell,
            oy + y * cell,
            ox + (x + 1) * cell,
            oy + (y + 1) * cell,
            fill="black",
            outline="black",
        )

    def draw():
        c.delete("all")
        for x in range(tw):
            rect(x, 0)
            rect(x, 1)
            rect(x, th - 2)
            rect(x, th - 1)
            if x % 2 == 0:
                rect(x, 3)
        for y in range(th):
            rect(0, y)
            rect(1, y)
            rect(tw - 2, y)
            rect(tw - 1, y)
            if y % 2 == 0:
                rect(3, y)
        for px, py in ((2, 2), (tw - 6, 2), (2, th - 6), (tw - 6, th - 6)):
            for y in range(py, py + 4):
                for x in range(px, px + 4):
                    rect(x, y)

        bits = frames[state["i"]]
        p = 0
        for y in range(H):
            for x in range(W):
                if bits[p]:
                    rect(x + M, y + M)
                p += 1
        bar_w = min(260, tw * cell)
        bar_x = (sw - bar_w) // 2
        c.create_rectangle(bar_x, max(0, oy - 22), bar_x + bar_w, max(0, oy - 16), fill="#dddddd", outline="")
        c.create_rectangle(
            bar_x,
            max(0, oy - 22),
            bar_x + int(bar_w * (state["i"] + 1) / len(frames)),
            max(0, oy - 16),
            fill="#333333",
            outline="",
        )
        c.create_text(
            sw // 2,
            max(10, oy - 34),
            fill="#444",
            font=("Arial", 14),
            text="Frame {}/{}   {} bytes   cell={}".format(state["i"] + 1, len(frames), len(data), cell),
        )
        state["i"] += 1
        if state["i"] >= len(frames):
            state["i"] = 0
            state["loop"] += 1
            if loops and state["loop"] >= loops:
                root.destroy()
                return
        root.after(int(delay * 1000), draw)

    draw()
    root.mainloop()


if __name__ == "__main__":
    main()
