"""Per-employee face enrollment and verification (OpenCV only, no dlib)."""

from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

import config
import detector

FACE_DIR = Path(__file__).resolve().parent / "face_models"
SIZE = (112, 112)
MATCH_THRESHOLD = 0.72  # cosine similarity; raise to be stricter
MIN_ENROLL_SAMPLES = 5
MAX_ENROLL_SAMPLES = 20

# Per-user: last successful face match (unix time)
_last_match_at: dict[int, float] = {}


def _ensure_dir() -> None:
    FACE_DIR.mkdir(parents=True, exist_ok=True)


def model_path(user_id: int) -> Path:
    return FACE_DIR / f"user_{user_id}.npz"


def thumb_path(user_id: int) -> Path:
    return FACE_DIR / f"user_{user_id}_thumb.jpg"


def has_enrollment(user_id: int) -> bool:
    path = model_path(user_id)
    if not path.is_file():
        return False
    try:
        data = np.load(path)
        return int(data["count"]) >= MIN_ENROLL_SAMPLES
    except Exception:
        return False


def enrollment_count(user_id: int) -> int:
    path = model_path(user_id)
    if not path.is_file():
        return 0
    try:
        return int(np.load(path)["count"])
    except Exception:
        return 0


def clear_enrollment(user_id: int) -> None:
    path = model_path(user_id)
    if path.is_file():
        path.unlink()
    thumb = thumb_path(user_id)
    if thumb.is_file():
        thumb.unlink()


def read_thumbnail(user_id: int) -> bytes | None:
    path = thumb_path(user_id)
    if not path.is_file():
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def _face_boxes(frame, yunet) -> list[tuple[int, int, int, int]]:
    boxes = detector.detect_faces(yunet, frame)
    height, width = frame.shape[:2]
    out = []
    for x, y, w, h in boxes:
        pad = int(0.15 * max(w, h))
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(width, x + w + pad)
        y2 = min(height, y + h + pad)
        if x2 - x1 < 40 or y2 - y1 < 40:
            continue
        out.append((x1, y1, x2, y2))
    return out


def _save_thumbnail(user_id: int, frame, box: tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = box
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return
    thumb = cv2.resize(crop, (96, 96))
    _ensure_dir()
    cv2.imwrite(str(thumb_path(user_id)), thumb, [int(cv2.IMWRITE_JPEG_QUALITY), 85])


def _crop_faces(frame, yunet) -> list[np.ndarray]:
    boxes = _face_boxes(frame, yunet)
    crops = []
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    for x1, y1, x2, y2 in boxes:
        face = gray[y1:y2, x1:x2]
        face = cv2.resize(face, SIZE)
        face = cv2.equalizeHist(face)
        crops.append(face)
    return crops


def _embed(face_gray: np.ndarray) -> np.ndarray:
    vec = face_gray.astype(np.float32).flatten() / 255.0
    norm = np.linalg.norm(vec) + 1e-6
    return vec / norm


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def enroll_from_frame(user_id: int, frame, yunet) -> dict:
    """Add face samples from one frame. Returns status dict."""
    _ensure_dir()
    crops = _crop_faces(frame, yunet)
    if not crops:
        return {"ok": False, "error": "No face found. Look at the camera.", "count": enrollment_count(user_id)}

    path = model_path(user_id)
    if path.is_file():
        data = np.load(path)
        embeds = list(data["embeds"])
    else:
        embeds = []

    added = 0
    for crop in crops:
        if len(embeds) >= MAX_ENROLL_SAMPLES:
            break
        embeds.append(_embed(crop))
        added += 1

    if added == 0 and len(embeds) >= MAX_ENROLL_SAMPLES:
        return {"ok": True, "count": len(embeds), "ready": True, "message": "Enrollment already complete."}

    boxes = _face_boxes(frame, yunet)
    if boxes:
        _save_thumbnail(user_id, frame, boxes[0])

    arr = np.stack(embeds, axis=0)
    np.savez_compressed(path, embeds=arr, count=np.array(len(embeds)))
    count = len(embeds)
    ready = count >= MIN_ENROLL_SAMPLES
    return {
        "ok": True,
        "count": count,
        "added": added,
        "ready": ready,
        "needed": max(0, MIN_ENROLL_SAMPLES - count),
        "message": "Face enrolled." if ready else f"Need {max(0, MIN_ENROLL_SAMPLES - count)} more samples.",
        "has_photo": thumb_path(user_id).is_file(),
    }


def verify(user_id: int, frame, yunet, require_desk_zone: bool = True) -> tuple[bool, float, str, tuple[int, int, int, int] | None]:
    """
    Return (matched, score, reason, box_xywh).
    matched=True only when this user's enrolled face is seen (and optionally in desk zone),
    or briefly held after a good match so looking away does not flip to Break.
    """
    if not has_enrollment(user_id):
        return False, 0.0, "not_enrolled", None

    data = np.load(model_path(user_id))
    embeds = data["embeds"]
    boxes = detector.detect_faces(yunet, frame)
    hold = float(getattr(config, "IDENTITY_HOLD_SECONDS", 12))
    now = time.time()

    if not boxes:
        if now - _last_match_at.get(user_id, 0) < hold:
            return True, 0.0, "hold", None
        return False, 0.0, "no_face", None

    height, width = frame.shape[:2]
    zone = detector.desk_zone(width, height)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    best = 0.0
    best_in_zone = False
    best_box: tuple[int, int, int, int] | None = None

    for x, y, w, h in boxes:
        in_zone = detector._in_zone((x, y, w, h), zone)
        if require_desk_zone and not in_zone:
            continue
        pad = int(0.15 * max(w, h))
        x1, y1 = max(0, x - pad), max(0, y - pad)
        x2, y2 = min(width, x + w + pad), min(height, y + h + pad)
        face = gray[y1:y2, x1:x2]
        if face.size == 0:
            continue
        face = cv2.resize(face, SIZE)
        face = cv2.equalizeHist(face)
        emb = _embed(face)
        for ref in embeds:
            score = _cosine(emb, ref)
            if score > best:
                best = score
                best_in_zone = in_zone
                best_box = (int(x), int(y), int(w), int(h))

    if best >= MATCH_THRESHOLD and (not require_desk_zone or best_in_zone):
        _last_match_at[user_id] = now
        return True, best, "matched", best_box

    if best >= MATCH_THRESHOLD and require_desk_zone and not best_in_zone:
        if now - _last_match_at.get(user_id, 0) < hold:
            return True, best, "hold", best_box
        return False, best, "outside_zone", best_box

    # Face seen but not this employee
    if best > 0.35 and boxes:
        _last_match_at.pop(user_id, None)
        return False, best, "mismatch", best_box

    if now - _last_match_at.get(user_id, 0) < hold:
        return True, best, "hold", best_box
    return False, best, "mismatch", best_box


def mark_identity_boxes(marks: list, matched: bool, matched_box: tuple[int, int, int, int] | None) -> list:
    """Only the enrolled employee may be labeled At desk / You."""
    out = []
    for m in marks:
        item = dict(m)
        if not matched or matched_box is None:
            item["at_desk"] = False
            if item.get("label") in {"Employee", "At desk", "You"} or m.get("at_desk"):
                item["label"] = "Other"
            out.append(item)
            continue
        mx, my, mw, mh = matched_box
        cx = item.get("x", 0) + item.get("w", 0) / 2
        cy = item.get("y", 0) + item.get("h", 0) / 2
        if mx <= cx <= mx + mw and my <= cy <= my + mh:
            item["at_desk"] = True
            item["label"] = "You"
        else:
            item["at_desk"] = False
            item["label"] = "Other"
        out.append(item)
    return out

