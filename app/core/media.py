# -*- coding: utf-8 -*-
"""Local media helpers: hashing, probing, validation and frame sampling."""
import base64
import hashlib
import os

import cv2


def md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def video_meta(path):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    dur = frames / fps if fps else 0
    return fps, frames, w, h, dur


def validate_video(path):
    """A video is usable only if OpenCV can open it and it has a real size."""
    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            return False
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return w > 0 and h > 0
    finally:
        cap.release()


def sample_frames(path, n=8, out_dir=None):
    n = max(1, min(int(n), 64))
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total == 0:
        cap.release(); return []
    idxs = [int(i * total / n) for i in range(n)]
    paths = []
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(i, total - 1))
        ok, frame = cap.read()
        if not ok:
            continue
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            p = os.path.join(out_dir, f"f{i:04d}.jpg")
            # imencode + binary write avoids cv2.imwrite silently failing
            # on Windows paths containing non-ASCII characters.
            ok_w, buf = cv2.imencode(".jpg", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
            if ok_w:
                with open(p, "wb") as wf:
                    wf.write(buf.tobytes())
                paths.append(p)
    cap.release()
    return paths


def frame_to_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
