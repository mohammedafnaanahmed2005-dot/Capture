"""
VisionAI - Core Object Detection Engine
Uses YOLOv4-tiny for real-time detection via webcam.
Falls back to simulation mode if model/webcam unavailable.
"""

import cv2
import numpy as np
import time
import os
import random
import math
from collections import defaultdict

# ── Target objects we care about ──────────────────────────────────────────────
# COCO classes relevant to our requirements (index → label)
TARGET_CLASSES = {
    'book': {'color': (0, 255, 128), 'icon': '📚'},
    'person': {'color': (0, 120, 255), 'icon': '🧍'},
    'cell phone': {'color': (255, 80, 80), 'icon': '📱'},
    'remote': {'color': (200, 100, 255), 'icon': '🎮'},  # closest to joystick/controller
    'keyboard': {'color': (255, 200, 0), 'icon': '⌨️'},
    'mouse': {'color': (0, 200, 200), 'icon': '🖱️'},
    'laptop': {'color': (255, 140, 0), 'icon': '💻'},
    'backpack': {'color': (180, 255, 100), 'icon': '🎒'},
    'handbag': {'color': (255, 100, 180), 'icon': '👜'},
    'scissors': {'color': (100, 180, 255), 'icon': '✂️'},
    'bottle': {'color': (80, 255, 200), 'icon': '🍶'},
    'cup': {'color': (255, 255, 80), 'icon': '☕'},
}

# Human body parts detected via OpenCV DNN face detector
BODY_PARTS = ['face', 'hand', 'body']

# Neon color palette for bounding boxes
NEON_COLORS = [
    (0, 255, 128),    # neon green
    (0, 120, 255),    # neon blue
    (255, 80, 80),    # neon red
    (200, 100, 255),  # neon purple
    (255, 200, 0),    # neon yellow
    (0, 200, 200),    # neon cyan
    (255, 140, 0),    # neon orange
]


class YOLODetector:
    """YOLOv4-tiny based object detector."""

    def __init__(self, model_dir='models'):
        self.model_dir = model_dir
        self.net = None
        self.classes = []
        self.output_layers = []
        self.face_cascade = None
        self.initialized = False
        self.simulation_mode = False
        self._load_model()

    def _load_model(self):
        cfg_path = os.path.join(self.model_dir, 'yolov4-tiny.cfg')
        weights_path = os.path.join(self.model_dir, 'yolov4-tiny.weights')
        names_path = os.path.join(self.model_dir, 'coco.names')

        # Load class names
        if os.path.exists(names_path):
            with open(names_path, 'r') as f:
                self.classes = [line.strip() for line in f.readlines()]
            print(f"[YOLO] Loaded {len(self.classes)} COCO classes")
        else:
            print("[YOLO] coco.names not found — using simulation mode")
            self.simulation_mode = True
            self.initialized = True
            return

        # Load YOLO network
        if os.path.exists(cfg_path) and os.path.exists(weights_path):
            try:
                self.net = cv2.dnn.readNet(weights_path, cfg_path)
                self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

                layer_names = self.net.getLayerNames()
                unconnected = self.net.getUnconnectedOutLayers()
                self.output_layers = [layer_names[i - 1] for i in unconnected.flatten()]
                print(f"[YOLO] Model loaded: {len(self.output_layers)} output layers")
                self.initialized = True
            except Exception as e:
                print(f"[YOLO] Failed to load model: {e} — enabling simulation mode")
                self.simulation_mode = True
                self.initialized = True
        else:
            print(f"[YOLO] Weights not found at {weights_path} — simulation mode active")
            self.simulation_mode = True
            self.initialized = True

        # Load Haar cascade for face detection
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        if os.path.exists(cascade_path):
            self.face_cascade = cv2.CascadeClassifier(cascade_path)
            print("[YOLO] Face cascade loaded")

    def detect(self, frame):
        """Run inference on a frame. Returns list of detection dicts."""
        if self.simulation_mode:
            return self._simulate_detections(frame)

        detections = []
        height, width = frame.shape[:2]

        # ── YOLO inference ────────────────────────────────────────────────────
        blob = cv2.dnn.blobFromImage(frame, 1/255.0, (416, 416),
                                     swapRB=True, crop=False)
        self.net.setInput(blob)
        outputs = self.net.forward(self.output_layers)

        boxes, confidences, class_ids = [], [], []

        for out in outputs:
            for detection in out:
                scores = detection[5:]
                class_id = int(np.argmax(scores))
                confidence = float(scores[class_id])

                if confidence > 0.35 and class_id < len(self.classes):
                    label = self.classes[class_id]
                    if label in TARGET_CLASSES:
                        cx, cy, w, h = (detection[0:4] * np.array(
                            [width, height, width, height])).astype(int)
                        x = cx - w // 2
                        y = cy - h // 2
                        boxes.append([x, y, w, h])
                        confidences.append(confidence)
                        class_ids.append(class_id)

        # Non-maximum suppression
        indices = cv2.dnn.NMSBoxes(boxes, confidences, 0.35, 0.45)
        if len(indices) > 0:
            for i in indices.flatten():
                x, y, w, h = boxes[i]
                label = self.classes[class_ids[i]]
                color = TARGET_CLASSES.get(label, {}).get('color', (0, 255, 0))
                detections.append({
                    'label': label,
                    'confidence': round(confidences[i], 3),
                    'bbox': [int(x), int(y), int(x + w), int(y + h)],
                    'color': color,
                })

        # ── Face detection (Haar cascade) ─────────────────────────────────────
        if self.face_cascade is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(50, 50))
            for (fx, fy, fw, fh) in faces:
                detections.append({
                    'label': 'face',
                    'confidence': 0.92,
                    'bbox': [int(fx), int(fy), int(fx + fw), int(fy + fh)],
                    'color': (255, 180, 50),
                })

        return detections

    # ── Simulation mode ────────────────────────────────────────────────────────
    def _simulate_detections(self, frame):
        """Generate fake detections for demo/testing without a real model."""
        height, width = frame.shape[:2]
        t = time.time()
        detections = []
        random.seed(int(t) % 1000)

        sim_objects = ['book', 'face', 'person', 'remote', 'cell phone',
                       'laptop', 'keyboard', 'bottle']

        num = random.randint(1, 4)
        chosen = random.sample(sim_objects, min(num, len(sim_objects)))

        for label in chosen:
            w = random.randint(80, 200)
            h = random.randint(80, 200)
            # oscillate position slightly for realism
            cx = int(width * 0.3 + random.uniform(-0.15, 0.15) * width
                     + 30 * math.sin(t + hash(label) % 100))
            cy = int(height * 0.4 + random.uniform(-0.15, 0.15) * height
                     + 20 * math.cos(t + hash(label) % 100))
            x1 = max(0, cx - w // 2)
            y1 = max(0, cy - h // 2)
            x2 = min(width, cx + w // 2)
            y2 = min(height, cy + h // 2)

            color = TARGET_CLASSES.get(label, {}).get('color',
                    NEON_COLORS[hash(label) % len(NEON_COLORS)])
            detections.append({
                'label': label,
                'confidence': round(random.uniform(0.62, 0.97), 3),
                'bbox': [x1, y1, x2, y2],
                'color': color,
            })

        return detections


def draw_detections(frame, detections):
    """Draw bounding boxes + labels on frame with neon HUD style."""
    for det in detections:
        x1, y1, x2, y2 = det['bbox']
        label = det['label']
        conf = det['confidence']
        color = det.get('color', (0, 255, 0))
        bgr_color = color  # already BGR

        # Outer glow (thick semi-transparent rect)
        overlay = frame.copy()
        cv2.rectangle(overlay, (x1 - 2, y1 - 2), (x2 + 2, y2 + 2),
                      bgr_color, 4)
        cv2.addWeighted(overlay, 0.4, frame, 0.6, 0, frame)

        # Main bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), bgr_color, 2)

        # Corner accents
        corner_len = 15
        cv2.line(frame, (x1, y1), (x1 + corner_len, y1), bgr_color, 3)
        cv2.line(frame, (x1, y1), (x1, y1 + corner_len), bgr_color, 3)
        cv2.line(frame, (x2, y1), (x2 - corner_len, y1), bgr_color, 3)
        cv2.line(frame, (x2, y1), (x2, y1 + corner_len), bgr_color, 3)
        cv2.line(frame, (x1, y2), (x1 + corner_len, y2), bgr_color, 3)
        cv2.line(frame, (x1, y2), (x1, y2 - corner_len), bgr_color, 3)
        cv2.line(frame, (x2, y2), (x2 - corner_len, y2), bgr_color, 3)
        cv2.line(frame, (x2, y2), (x2, y2 - corner_len), bgr_color, 3)

        # Label background pill
        text = f"{label.upper()}  {conf * 100:.0f}%"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.55
        thickness = 1
        (tw, th), baseline = cv2.getTextSize(text, font, font_scale, thickness)
        pad = 5
        lx1, ly1 = x1, max(0, y1 - th - 2 * pad)
        lx2, ly2 = x1 + tw + 2 * pad, y1

        cv2.rectangle(frame, (lx1, ly1), (lx2, ly2), bgr_color, -1)
        cv2.putText(frame, text,
                    (lx1 + pad, ly2 - pad),
                    font, font_scale, (0, 0, 0), thickness + 1, cv2.LINE_AA)
        cv2.putText(frame, text,
                    (lx1 + pad, ly2 - pad),
                    font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

    # HUD overlay — frame info
    timestamp = time.strftime('%H:%M:%S')
    cv2.putText(frame, f"VisionAI  |  {timestamp}",
                (10, frame.shape[0] - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 255, 200), 1, cv2.LINE_AA)

    return frame
