#!/usr/bin/env python3
"""Decode QRFT screenshots.

Install decoder dependencies on the receiver machine:

    python -m pip install numpy opencv-python requests

Folder mode:

    python qrft_recv.py --folder snapshot --out decoded_test.txt

Snapshot mode:

    python qrft_recv.py --url "https://your-kvm-host/api/streamer/snapshot?save=1" --out decoded_test.txt
"""

import argparse
import glob
import os
import struct
import time
import zlib

import cv2
import numpy as np

W, H, M = 260, 120, 6
HDR, REP = 32, 5
MAGIC, VER = b"QF10", 1
TW, TH = W + 2 * M, H + 2 * M


def majority_header(bits):
    copies = []
    for r in range(REP):
        start = r * HDR * 8
        copies.append(bits[start : start + HDR * 8])
    voted = []
    for i in range(HDR * 8):
        voted.append(1 if sum(c[i] for c in copies) >= (REP // 2 + 1) else 0)
    return bytes_from_bits(voted, HDR)


def bytes_from_bits(bits, nbytes=None):
    if nbytes is None:
        nbytes = len(bits) // 8
    out = bytearray()
    for i in range(nbytes):
        v = 0
        for b in bits[i * 8 : i * 8 + 8]:
            v = (v << 1) | int(b)
        out.append(v)
    return bytes(out)


def find_frame(gray):
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _thr, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Prefer the sender's explicit top border. In KVM screenshots the outer
    # desktop/window chrome and black letterbox bars can form larger connected
    # components than the transfer frame, so contour area is a poor first cue.
    projection_box = find_frame_by_projection(bw, gray.shape)
    if projection_box is not None:
        return projection_box

    contours, _hier = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    expected = TW / float(TH)
    best = None
    best_score = -1.0
    ih, iw = gray.shape[:2]
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w < iw * 0.25 or h < ih * 0.25:
            continue
        ar = w / float(h)
        ar_score = max(0.0, 1.0 - abs(ar - expected) / expected)
        area_score = (w * h) / float(iw * ih)
        score = ar_score * 3.0 + area_score
        if score > best_score:
            best_score = score
            best = (x, y, w, h)
    return best


def dark_runs(row):
    runs = []
    start = None
    for i, value in enumerate(row):
        if value and start is None:
            start = i
        if (not value or i == len(row) - 1) and start is not None:
            end = i - 1 if not value else i
            runs.append((start, end, end - start + 1))
            start = None
    return runs


def find_frame_by_projection(bw, shape):
    ih, iw = shape[:2]
    expected_w = min(iw, int(round(TW * min(iw / float(TW), ih / float(TH)))))
    min_w = max(200, int(expected_w * 0.75))
    candidates = []
    for y in range(0, ih):
        runs = [r for r in dark_runs(bw[y] > 0) if r[2] >= min_w]
        for x1, x2, width in runs:
            if x1 <= 2 or x2 >= iw - 2:
                continue
            cell = int(round(width / float(TW)))
            if cell < 2:
                continue
            expected_w = TW * cell
            expected_h = TH * cell
            if x1 + expected_w > iw + cell or y + expected_h > ih + cell:
                continue
            score = expected_w - abs(width - expected_w) * 3
            candidates.append((score, x1, y, expected_w, expected_h, cell))
    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[2], -item[0]))
    for _score, x, y, width, expected_h, cell in candidates[:20]:
        if ih - y < expected_h * 0.8:
            continue
        side_h = min(ih - y, max(8, int(round(TH * cell))))
        side_w = max(2, int(round(cell * 1.5)))
        left = bw[y : y + side_h, x : min(iw, x + side_w)] > 0
        right_x = min(iw - side_w, int(round(x + width - side_w)))
        right = bw[y : y + side_h, right_x : right_x + side_w] > 0
        if left.size and right.size and np.mean(left) > 0.25 and np.mean(right) > 0.25:
            return (x, y, width, expected_h)
    _score, x, y, width, expected_h, _cell = candidates[0]
    return (x, y, width, expected_h)


def sample_bits(gray, box):
    x0, y0, bw, bh = box
    crop = gray[y0 : y0 + bh, x0 : x0 + bw]
    thr, _mask = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cell_x = bw / float(TW)
    cell_y = bh / float(TH)
    bits = []
    for gy in range(H):
        cy = y0 + (gy + M + 0.5) * cell_y
        ry = max(1, int(cell_y * 0.25))
        y1 = max(0, int(cy - ry))
        y2 = min(gray.shape[0], int(cy + ry + 1))
        for gx in range(W):
            cx = x0 + (gx + M + 0.5) * cell_x
            rx = max(1, int(cell_x * 0.25))
            x1 = max(0, int(cx - rx))
            x2 = min(gray.shape[1], int(cx + rx + 1))
            patch = gray[y1:y2, x1:x2]
            bits.append(1 if float(np.mean(patch)) < thr else 0)
    return bits


def decode_image(path):
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None, "read failed"
    box = find_frame(img)
    if box is None:
        return None, "frame not found"
    bits = sample_bits(img, box)
    h = majority_header(bits)
    try:
        magic, ver, hlen, idx, total, fsize, plen, fcrc, pcrc, _res = struct.unpack(
            ">4sBBHHIHII8s", h
        )
    except struct.error as exc:
        return None, "bad header: {}".format(exc)
    if magic != MAGIC or ver != VER or hlen != HDR:
        return None, "bad magic/version/header"
    if total < 1 or idx >= total or plen > (W * H // 8 - HDR * REP):
        return None, "bad indexes idx={} total={} plen={}".format(idx, total, plen)
    payload_bits = bits[HDR * REP * 8 : HDR * REP * 8 + plen * 8]
    payload = bytes_from_bits(payload_bits, plen)
    if (zlib.crc32(payload) & 0xFFFFFFFF) != pcrc:
        return None, "frame crc failed idx={}".format(idx)
    return {
        "idx": idx,
        "total": total,
        "file_size": fsize,
        "payload_len": plen,
        "file_crc": fcrc,
        "payload": payload,
    }, None


def snapshot_to_file(url, path, verify_tls=True):
    try:
        import requests
    except ImportError as exc:
        raise SystemExit("requests is required for --url mode") from exc
    r = requests.get(url, timeout=5, verify=verify_tls)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)


def collect_files(folder):
    pats = ["*.png", "*.jpg", "*.jpeg", "*.bmp"]
    out = []
    for pat in pats:
        out.extend(glob.glob(os.path.join(folder, pat)))
    return sorted(out)


def clear_image_files(folder):
    os.makedirs(folder, exist_ok=True)
    removed = 0
    for path in collect_files(folder):
        try:
            os.remove(path)
            removed += 1
        except OSError as exc:
            print("warning: could not remove {}: {}".format(path, exc))
    print("cleared {} image files from {}".format(removed, folder))


def ingest(paths, frames):
    meta = None
    ok = 0
    for path in paths:
        frame, err = decode_image(path)
        name = os.path.basename(path)
        if err:
            print("skip {}: {}".format(name, err))
            continue
        if meta is None:
            meta = frame
        elif (
            frame["total"] != meta["total"]
            or frame["file_size"] != meta["file_size"]
            or frame["file_crc"] != meta["file_crc"]
        ):
            print("skip {}: file metadata mismatch".format(name))
            continue
        if frame["idx"] not in frames:
            ok += 1
        frames[frame["idx"]] = frame["payload"]
        print("ok {}: frame {}/{}".format(name, frame["idx"] + 1, frame["total"]))
    return meta, ok


def write_if_complete(meta, frames, out_path):
    if meta is None:
        print("no valid frames")
        return False
    missing = [i for i in range(meta["total"]) if i not in frames]
    got = meta["total"] - len(missing)
    print("received {}/{} frames ({:.1f}%)".format(got, meta["total"], got * 100.0 / meta["total"]))
    if missing:
        print("missing:", ",".join(str(i + 1) for i in missing))
        return False
    data = b"".join(frames[i] for i in range(meta["total"]))[: meta["file_size"]]
    crc = zlib.crc32(data) & 0xFFFFFFFF
    if crc != meta["file_crc"]:
        print("file crc failed: got {:08x}, expected {:08x}".format(crc, meta["file_crc"]))
        return False
    name, file_data = unpack_named_payload(data)
    final_path = output_path_for_name(out_path, name)
    with open(final_path, "wb") as f:
        f.write(file_data)
    if name:
        print("wrote {} ({} bytes, crc {:08x}, source name {})".format(final_path, len(file_data), crc, name))
    else:
        print("wrote {} ({} bytes, crc {:08x})".format(final_path, len(file_data), crc))
    return True


def unpack_named_payload(data):
    if len(data) < 2:
        return "", data
    name_len = struct.unpack(">H", data[:2])[0]
    if name_len < 1 or name_len > 512 or 2 + name_len > len(data):
        return "", data
    raw = data[2 : 2 + name_len]
    try:
        name = raw.decode("utf-8")
    except UnicodeDecodeError:
        return "", data
    safe = sanitize_filename(name)
    if not safe:
        return "", data
    return safe, data[2 + name_len :]


def sanitize_filename(name):
    base = os.path.basename(name.replace("\\", "/"))
    bad = '<>:"/\\|?*\0'
    base = "".join("_" if ch in bad or ord(ch) < 32 else ch for ch in base).strip()
    if base in ("", ".", ".."):
        return ""
    return base


def output_path_for_name(out_path, name):
    if not name:
        return out_path
    if out_path.endswith(os.sep) or (os.path.exists(out_path) and os.path.isdir(out_path)):
        folder = out_path
    else:
        folder = os.path.dirname(out_path) or "."
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", default="snapshot")
    ap.add_argument("--out", default="decoded_test.txt")
    ap.add_argument("--url", default="")
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--max-captures", type=int, default=0)
    ap.add_argument("--insecure", action="store_true", help="allow self-signed HTTPS certificates")
    ap.add_argument("--clear-folder", action="store_true", help="clear existing snapshot images before URL capture")
    ap.add_argument("--keep-folder", action="store_true", help="keep existing snapshot images before URL capture")
    args = ap.parse_args()

    frames = {}
    meta = None
    if args.url:
        os.makedirs(args.folder, exist_ok=True)
        if args.clear_folder or not args.keep_folder:
            clear_image_files(args.folder)
        n = 0
        while True:
            n += 1
            path = os.path.join(args.folder, "cap_{:05d}.jpg".format(n))
            snapshot_to_file(args.url, path, verify_tls=not args.insecure)
            got_meta, _ok = ingest([path], frames)
            if got_meta is not None:
                meta = got_meta if meta is None else meta
            if write_if_complete(meta, frames, args.out):
                break
            if args.max_captures and n >= args.max_captures:
                break
            time.sleep(args.interval)
    else:
        meta, _ok = ingest(collect_files(args.folder), frames)
        write_if_complete(meta, frames, args.out)


if __name__ == "__main__":
    main()
