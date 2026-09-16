"""Desk presence: YuNet face (webcam close-up) + YOLO person, with a desk-zone overlay."""

from __future__ import annotations

import time
import urllib.request
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

MODEL_DIR = Path(__file__).with_name("yolo_model")
ONNX_PATH = MODEL_DIR / "yolov5n.onnx"
YUNET_PATH = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
ONNX_URLS = [
    "https://github.com/ultralytics/yolov5/releases/download/v7.0/yolov5n.onnx",
]
YUNET_URLS = [
    "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx?download=true",
]
INPUT = 640
CONFIDENCE = 0.18
NMS = 0.45
PERSON_CLASS = 0
FACE_SCORE = 0.45
HOLD_SECONDS = 2.8
_hold_until = 0.0


def ensure_model() -> None:
    MODEL_DIR.mkdir(exist_ok=True)
    if not (ONNX_PATH.exists() and ONNX_PATH.stat().st_size > 1_000_000):
        last_error = None
        for url in ONNX_URLS:
            try:
                print("Downloading YOLOv5n (first run only, ~4 MB)...")
                urllib.request.urlretrieve(url, ONNX_PATH)
                if ONNX_PATH.stat().st_size > 1_000_000:
                    break
            except Exception as exc:
                last_error = exc
        else:
            raise RuntimeError(f"Could not download YOLOv5n: {last_error}")
    if YUNET_PATH.exists() and YUNET_PATH.stat().st_size > 50_000:
        return
    last_error = None
    for url in YUNET_URLS:
        try:
            print("Downloading YuNet face model (first run only)...")
            urllib.request.urlretrieve(url, YUNET_PATH)
            if YUNET_PATH.stat().st_size > 50_000:
                return
        except Exception as exc:
            last_error = exc
    print(f"YuNet download skipped ({last_error}). Face close-ups may miss until the file is present.")


def load_net():
    ensure_model()
    # Keep OpenCV on one thread — lower RAM/CPU on small VPS
    try:
        cv2.setNumThreads(1)
    except Exception:
        pass
    net = cv2.dnn.readNetFromONNX(str(ONNX_PATH))
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    yunet = None
    if YUNET_PATH.exists():
        try:
            yunet = cv2.FaceDetectorYN.create(str(YUNET_PATH), "", (320, 320), FACE_SCORE, 0.3, 5000)
        except Exception as exc:
            print(f"YuNet did not load ({exc}). Using YOLO only.")
    return net, yunet


def desk_zone(width: int, height: int) -> tuple[int, int, int, int]:
    return (
        int(width * 0.08),
        int(height * 0.04),
        int(width * 0.92),
        int(height * 0.98),
    )


def _in_zone(box, zone, overlap=0.08) -> bool:
    x, y, w, h = box
    zx1, zy1, zx2, zy2 = zone
    cx, cy = x + w / 2, y + h / 2
    if zx1 <= cx <= zx2 and zy1 <= cy <= zy2:
        return True
    ix1, iy1 = max(zx1, x), max(zy1, y)
    ix2, iy2 = min(zx2, x + w), min(zy2, y + h)
    if ix2 <= ix1 or iy2 <= iy1:
        return False
    return ((ix2 - ix1) * (iy2 - iy1)) / max(w * h, 1) > overlap


def _yolo_rows(raw) -> np.ndarray:
    if isinstance(raw, (tuple, list)):
        raw = raw[0]
    arr = np.asarray(raw)
    if arr.ndim == 3:
        arr = arr[0]
    return arr


def detect_faces(yunet, frame) -> list:
    if yunet is None:
        return []
    height, width = frame.shape[:2]
    small = cv2.resize(frame, (320, 320))
    try:
        yunet.setInputSize((320, 320))
    except TypeError:
        yunet.setInputSize(320, 320)
    result = yunet.detect(small)
    faces = result[1] if isinstance(result, tuple) and len(result) > 1 else result
    if faces is None:
        return []
    boxes = []
    sx, sy = width / 320, height / 320
    for row in np.asarray(faces):
        x, y, w, h = [float(v) for v in row[:4]]
        score = float(row[14]) if len(row) > 14 else float(row[4])
        if score < FACE_SCORE:
            continue
        boxes.append([int(x * sx), int(y * sy), max(1, int(w * sx)), max(1, int(h * sy))])
    return boxes


def detect_people(frame, net) -> tuple[list, list]:
    height, width = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (INPUT, INPUT), swapRB=True, crop=False)
    net.setInput(blob)
    rows = _yolo_rows(net.forward())
    boxes, scores = [], []
    scale_x, scale_y = width / INPUT, height / INPUT
    for row in rows:
        objectness = float(row[4])
        class_scores = row[5:]
        class_id = int(np.argmax(class_scores))
        confidence = objectness * float(class_scores[class_id])
        if class_id != PERSON_CLASS or confidence < CONFIDENCE:
            continue
        cx, cy, w, h = row[:4]
        x = int((cx - w / 2) * scale_x)
        y = int((cy - h / 2) * scale_y)
        bw, bh = int(w * scale_x), int(h * scale_y)
        boxes.append([x, y, bw, bh])
        scores.append(confidence)
    if not boxes:
        return [], []
    indices = cv2.dnn.NMSBoxes(boxes, scores, CONFIDENCE, NMS)
    if len(indices) == 0:
        return [], []
    keep = np.array(indices).flatten()
    return [boxes[i] for i in keep], [scores[i] for i in keep]


def annotate(frame, net, yunet=None) -> tuple[bool, object, float, list]:
    global _hold_until
    height, width = frame.shape[:2]
    zone = desk_zone(width, height)
    faces = detect_faces(yunet, frame)
    people, people_scores = ([], []) if faces else detect_people(frame, net)
    found = False
    best = 0.0

    marks = []
    for (x, y, w, h) in faces:
        at_desk = _in_zone((x, y, w, h), zone)
        if at_desk:
            found = True
            best = max(best, 0.99)
            color, label = (0, 0, 255), "Employee"
        else:
            color, label = (255, 0, 0), "Face"
        marks.append({"x": x, "y": y, "w": w, "h": h, "at_desk": at_desk, "label": label})
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        cv2.putText(frame, label, (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    for (x, y, w, h), conf in zip(people, people_scores):
        at_desk = _in_zone((x, y, w, h), zone)
        if at_desk:
            found = True
            best = max(best, conf)
            color, label = (0, 0, 255), f"Employee: {conf:.2f}"
        else:
            color, label = (255, 0, 0), f"Person: {conf:.2f}"
        marks.append({"x": x, "y": y, "w": w, "h": h, "at_desk": at_desk, "label": label})
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        cv2.putText(frame, label, (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    now = time.time()
    if found:
        _hold_until = now + HOLD_SECONDS
    present = found or now < _hold_until

    zx1, zy1, zx2, zy2 = zone
    cv2.rectangle(frame, (zx1, zy1), (zx2, zy2), (0, 255, 0), 2)
    status = "Status: PRESENT" if present else "Status: ABSENT"
    color = (0, 255, 0) if present else (0, 0, 255)
    cv2.putText(frame, status, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cv2.putText(frame, f"Time: {stamp}", (12, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return present, frame, best, marks
