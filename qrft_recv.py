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
from urllib.parse import quote_plus, urlsplit, urlunsplit

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

    vertical_box = find_frame_by_vertical_edge(bw, gray.shape)
    if vertical_box is not None:
        return vertical_box

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


def true_runs(values):
    runs = []
    padded = np.r_[False, values, False]
    changes = np.flatnonzero(padded[1:] != padded[:-1])
    for start, end in zip(changes[0::2], changes[1::2]):
        runs.append((int(start), int(end - 1), int(end - start)))
    return runs


def find_frame_by_vertical_edge(bw, shape):
    ih, iw = shape[:2]
    dark = bw > 0
    best = None
    for x in range(3, iw - 3):
        count = int(np.sum(dark[:, x]))
        if count < ih * 0.6:
            continue
        for y1, _y2, height in true_runs(dark[:, x]):
            if y1 < 35 or height < ih * 0.45:
                continue
            cell = int(round(height / float(TH)))
            if cell < 2:
                continue
            expected_h = TH * cell
            expected_w = TW * cell
            if abs(height - expected_h) > max(4, cell * 3):
                continue
            if x + expected_w > iw + cell or y1 + expected_h > ih + cell:
                continue
            top = dark[y1 : min(ih, y1 + max(2, cell * 2)), x : min(iw, x + expected_w)]
            left = dark[y1 : min(ih, y1 + expected_h), x : min(iw, x + max(2, cell * 2))]
            if top.size and left.size and np.mean(top) > 0.45 and np.mean(left) > 0.45:
                score = height - abs(height - expected_h) * 5 - x * 0.01
                if best is None or score > best[0]:
                    best = (score, x, y1, expected_w, expected_h)
    if best is None:
        return None
    _score, x, y, width, height = best
    return (x, y, width, height)


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
    dark = bw > 0
    row_counts = np.sum(dark, axis=1)
    ys = np.flatnonzero(row_counts >= min_w)
    candidates = []
    for y in ys:
        xs = np.flatnonzero(dark[y])
        if xs.size == 0:
            continue
        x1 = int(xs[0])
        x2 = int(xs[-1])
        width = x2 - x1 + 1
        if x1 <= 2 or x2 >= iw - 2 or width < min_w:
            continue
        cell = int(round(width / float(TW)))
        if cell < 2:
            continue
        expected_w = TW * cell
        expected_h = TH * cell
        if x1 + expected_w > iw + cell or y + expected_h > ih + cell:
            continue
        score = expected_w - abs(width - expected_w) * 3
        candidates.append((score, x1, int(y), expected_w, expected_h, cell))
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
    rx = max(1, int(cell_x * 0.25))
    ry = max(1, int(cell_y * 0.25))
    xs = x0 + (np.arange(W) + M + 0.5) * cell_x
    ys = y0 + (np.arange(H) + M + 0.5) * cell_y
    x1 = np.clip((xs - rx).astype(np.int32), 0, gray.shape[1])
    x2 = np.clip((xs + rx + 1).astype(np.int32), 0, gray.shape[1])
    y1 = np.clip((ys - ry).astype(np.int32), 0, gray.shape[0])
    y2 = np.clip((ys + ry + 1).astype(np.int32), 0, gray.shape[0])
    integral = cv2.integral(gray, sdepth=cv2.CV_64F)
    sums = (
        integral[y2[:, None], x2[None, :]]
        - integral[y1[:, None], x2[None, :]]
        - integral[y2[:, None], x1[None, :]]
        + integral[y1[:, None], x1[None, :]]
    )
    areas = (y2 - y1)[:, None] * (x2 - x1)[None, :]
    means = sums / np.maximum(areas, 1)
    return (means < thr).astype(np.uint8).ravel().tolist()


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


def request_client(session=None):
    if session is not None:
        return session
    try:
        import requests
    except ImportError as exc:
        raise SystemExit("requests is required for URL mode") from exc
    return requests


def snapshot_to_file(url, path, verify_tls=True, session=None):
    client = request_client(session)
    r = client.get(url, timeout=5, verify=verify_tls)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)


def derive_advance_url(snapshot_url, key):
    parts = urlsplit(snapshot_url)
    query = "key={}&finish=1".format(quote_plus(api_key_name(key)))
    return urlunsplit((parts.scheme, parts.netloc, "/api/hid/events/send_key", query, ""))


def derive_mouse_relative_url(snapshot_url, dx, dy):
    parts = urlsplit(snapshot_url)
    query = "delta_x={}&delta_y={}".format(int(dx), int(dy))
    return urlunsplit((parts.scheme, parts.netloc, "/api/hid/events/send_mouse_relative", query, ""))


def park_mouse_relative(snapshot_url, dx, dy, steps, verify_tls=True, method="post", session=None):
    url = derive_mouse_relative_url(snapshot_url, dx, dy)
    for _i in range(max(1, int(steps))):
        call_url(url, verify_tls=verify_tls, method=method, session=session)


def key_url(template, snapshot_url, key):
    if template:
        return template.format(key=quote_plus(api_key_name(key)))
    return derive_advance_url(snapshot_url, str(key))


def api_key_name(key):
    key = str(key)
    if len(key) == 1 and key.isdigit():
        return "Digit{}".format(key)
    if len(key) == 1 and key.isalpha():
        return "Key{}".format(key.upper())
    aliases = {
        "return": "Enter",
        "space": "Space",
        "esc": "Escape",
        "escape": "Escape",
        "backspace": "Backspace",
        "left": "ArrowLeft",
        "right": "ArrowRight",
        "up": "ArrowUp",
        "down": "ArrowDown",
    }
    return aliases.get(key.lower(), key)


def send_key(template, snapshot_url, key, verify_tls=True, method="post", session=None):
    send_advance(key_url(template, snapshot_url, key), verify_tls=verify_tls, method=method, session=session)


def send_frame_select(template, snapshot_url, frame_idx, verify_tls=True, method="post", key_delay=0.03, session=None):
    for ch in str(frame_idx + 1):
        send_key(template, snapshot_url, ch, verify_tls=verify_tls, method=method, session=session)
        if key_delay:
            time.sleep(key_delay)
    send_key(template, snapshot_url, "Enter", verify_tls=verify_tls, method=method, session=session)


def send_advance(url, verify_tls=True, method="post", session=None):
    client = request_client(session)
    method = method.lower()
    if method == "get":
        r = client.get(url, timeout=5, verify=verify_tls)
    else:
        r = client.post(url, timeout=5, verify=verify_tls)
        if r.status_code in (404, 405, 501):
            r = client.get(url, timeout=5, verify=verify_tls)
    r.raise_for_status()


def call_url(url, verify_tls=True, method="post", session=None):
    if not url:
        return
    client = request_client(session)
    if method.lower() == "get":
        r = client.get(url, timeout=5, verify=verify_tls)
    else:
        r = client.post(url, timeout=5, verify=verify_tls)
        if r.status_code in (404, 405, 501):
            r = client.get(url, timeout=5, verify=verify_tls)
    r.raise_for_status()


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


def capture_decode_accept(args, session, n, frames, meta):
    path = os.path.join(args.folder, "cap_{:05d}.jpg".format(n))
    t0 = time.perf_counter()
    snapshot_to_file(args.url, path, verify_tls=not args.insecure, session=session)
    t1 = time.perf_counter()
    frame, err = decode_image(path)
    t2 = time.perf_counter()
    if err:
        print("skip {}: {}".format(os.path.basename(path), err))
    else:
        meta, _is_new = accept_frame(frame, frames, meta, os.path.basename(path))
    if args.profile:
        print("time {}: snapshot={:.3f}s decode={:.3f}s".format(os.path.basename(path), t1 - t0, t2 - t1))
    return meta, frame, err


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


def accept_frame(frame, frames, meta, name):
    if frame is None:
        return meta, False
    if meta is None:
        meta = frame
    elif (
        frame["total"] != meta["total"]
        or frame["file_size"] != meta["file_size"]
        or frame["file_crc"] != meta["file_crc"]
    ):
        print("skip {}: file metadata mismatch".format(name))
        return meta, False
    is_new = frame["idx"] not in frames
    frames[frame["idx"]] = frame["payload"]
    print("ok {}: frame {}/{}{}".format(name, frame["idx"] + 1, frame["total"], " new" if is_new else " dup"))
    return meta, is_new


def write_if_complete(meta, frames, out_path):
    if meta is None:
        print("no valid frames")
        return False
    missing = [i for i in range(meta["total"]) if i not in frames]
    got = meta["total"] - len(missing)
    print("received {}/{} frames ({:.1f}%)".format(got, meta["total"], got * 100.0 / meta["total"]))
    if missing:
        print("missing:", format_missing(missing))
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


def format_missing(missing, limit=16):
    shown = ",".join(str(i + 1) for i in missing[:limit])
    if len(missing) > limit:
        shown += ",...(+{})".format(len(missing) - limit)
    return shown


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
    ap.add_argument("--advance-key", default="", help="derive a KVM send_key URL and press this key after each capture")
    ap.add_argument("--advance-url", default="", help="explicit URL to call after each capture to advance the sender")
    ap.add_argument("--key-url-template", default="", help="URL template for key presses, using {key} placeholder")
    ap.add_argument("--advance-method", default="post", choices=("post", "get"), help="HTTP method for --advance-url")
    ap.add_argument("--advance-settle", type=float, default=0.25, help="seconds to wait after advancing before next capture")
    ap.add_argument("--adaptive-settle", action="store_true", help="poll immediately after targeted advance instead of sleeping a fixed settle time")
    ap.add_argument("--scan-captures", type=int, default=0, help="capture this many frames before targeted repair, useful with sender --auto-advance")
    ap.add_argument("--targeted", action="store_true", help="request missing frame numbers instead of only pressing next")
    ap.add_argument("--poll-delay", type=float, default=0.15, help="delay between retry captures while waiting for a target frame")
    ap.add_argument("--target-retries", type=int, default=4, help="deprecated alias for --target-timeout polling")
    ap.add_argument("--target-timeout", type=float, default=3.0, help="seconds to wait for a requested target frame")
    ap.add_argument("--park-mouse-url", default="", help="optional URL to call once before capture to move/hide the pointer")
    ap.add_argument("--park-mouse-relative", action="store_true", help="move relative HID pointer before capture")
    ap.add_argument("--park-mouse-dx", type=int, default=32767, help="relative pointer X delta for --park-mouse-relative")
    ap.add_argument("--park-mouse-dy", type=int, default=-32768, help="relative pointer Y delta for --park-mouse-relative")
    ap.add_argument("--park-mouse-steps", type=int, default=3, help="number of relative pointer moves before capture")
    ap.add_argument("--profile", action="store_true", help="print snapshot/decode/key timing")
    args = ap.parse_args()
    if args.insecure:
        try:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except ImportError:
            pass

    frames = {}
    meta = None
    if args.url:
        try:
            import requests
        except ImportError as exc:
            raise SystemExit("requests is required for URL mode") from exc
        session = requests.Session()
        os.makedirs(args.folder, exist_ok=True)
        if args.clear_folder or not args.keep_folder:
            clear_image_files(args.folder)
        if args.park_mouse_relative:
            park_mouse_relative(
                args.url,
                args.park_mouse_dx,
                args.park_mouse_dy,
                args.park_mouse_steps,
                verify_tls=not args.insecure,
                method=args.advance_method,
                session=session,
            )
        call_url(args.park_mouse_url, verify_tls=not args.insecure, method=args.advance_method, session=session)
        advance_url = args.advance_url
        if not advance_url and args.advance_key:
            advance_url = derive_advance_url(args.url, args.advance_key)
        n = 0
        if args.scan_captures:
            for _i in range(args.scan_captures):
                n += 1
                meta, _frame, _err = capture_decode_accept(args, session, n, frames, meta)
                if write_if_complete(meta, frames, args.out):
                    return
                if args.max_captures and n >= args.max_captures:
                    return
                if args.interval:
                    time.sleep(args.interval)
        while True:
            if args.targeted and meta:
                missing = [i for i in range(meta["total"]) if i not in frames]
                target = missing[0] if missing else None
                if target is not None:
                    kt0 = time.perf_counter()
                    send_frame_select(args.key_url_template, args.url, target, verify_tls=not args.insecure, method=args.advance_method, session=session)
                    if not args.adaptive_settle:
                        time.sleep(args.advance_settle)
                    kt1 = time.perf_counter()
                    if args.profile:
                        print("time target {}: key+settle={:.3f}s".format(target + 1, kt1 - kt0))
                    deadline = time.perf_counter() + args.target_timeout
                    attempts = 0
                    while time.perf_counter() < deadline:
                        attempts += 1
                        n += 1
                        meta, frame, _err = capture_decode_accept(args, session, n, frames, meta)
                        if frame and frame["idx"] == target and target in frames:
                            break
                        if args.max_captures and n >= args.max_captures:
                            break
                        time.sleep(args.poll_delay)
                    if args.profile and target not in frames:
                        print("target {} not seen after {} captures".format(target + 1, attempts))
                    if write_if_complete(meta, frames, args.out):
                        break
                    if args.max_captures and n >= args.max_captures:
                        break
                    continue
            n += 1
            meta, _frame, _err = capture_decode_accept(args, session, n, frames, meta)
            if write_if_complete(meta, frames, args.out):
                break
            if args.max_captures and n >= args.max_captures:
                break
            if advance_url:
                kt0 = time.perf_counter()
                send_advance(advance_url, verify_tls=not args.insecure, method=args.advance_method, session=session)
                time.sleep(args.advance_settle)
                if args.profile:
                    print("time advance: key+settle={:.3f}s".format(time.perf_counter() - kt0))
            else:
                time.sleep(args.interval)
    else:
        meta, _ok = ingest(collect_files(args.folder), frames)
        write_if_complete(meta, frames, args.out)


if __name__ == "__main__":
    main()
