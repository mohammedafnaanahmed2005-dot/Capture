"""
VisionAI - Flask Backend
Serves the dashboard and streams live detection data via Socket.IO.
"""

import os
import cv2
import base64
import json
import time
import threading
import numpy as np
from datetime import datetime
from flask import Flask, render_template, jsonify, request, Response
from flask_socketio import SocketIO, emit
from flask_cors import CORS

import detector as det_module
import storage

# ── App Setup ──────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY'] = 'visionai-secret-2026'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

# ── Globals ────────────────────────────────────────────────────────────────────
detector = None
camera = None
camera_lock = threading.Lock()
stream_active = False
detection_thread = None

# Latest frame state (shared between thread and clients)
latest_frame_b64 = None
latest_detections = []
frame_count = 0
fps_tracker = []
current_fps = 0


def init_detector():
    global detector
    print("[APP] Initializing YOLO detector...")
    detector = det_module.YOLODetector(model_dir='models')
    mode = "SIMULATION" if detector.simulation_mode else "LIVE YOLO"
    print(f"[APP] Detector ready — mode: {mode}")


def open_camera():
    global camera
    with camera_lock:
        if camera is not None:
            camera.release()
        # Try camera indices 0, 1, 2
        for idx in range(3):
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 30)
                camera = cap
                print(f"[APP] Webcam opened at index {idx}")
                return True
        # Fallback: create a dark frame with text
        print("[APP] No webcam found — using placeholder frame")
        camera = None
        return False


def make_placeholder_frame():
    """Generate a dark placeholder frame when no webcam is available."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Subtle grid
    for y in range(0, 480, 40):
        cv2.line(frame, (0, y), (640, y), (20, 20, 20), 1)
    for x in range(0, 640, 40):
        cv2.line(frame, (x, 0), (x, 480), (20, 20, 20), 1)

    cv2.putText(frame, "NO CAMERA", (180, 200),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 200, 100), 2, cv2.LINE_AA)
    cv2.putText(frame, "Simulation Mode Active", (140, 250),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 200, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, "Connect a webcam for live detection",
                (80, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (150, 150, 150), 1, cv2.LINE_AA)
    ts = datetime.now().strftime('%H:%M:%S')
    cv2.putText(frame, f"VisionAI  |  {ts}", (10, 468),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 255, 200), 1, cv2.LINE_AA)
    return frame


def detection_loop():
    """Background thread: capture → detect → annotate → broadcast."""
    global latest_frame_b64, latest_detections, frame_count
    global current_fps, fps_tracker, stream_active

    stream_active = True
    has_camera = open_camera()

    print("[STREAM] Detection loop started")

    while stream_active:
        loop_start = time.time()

        # ── Grab frame ────────────────────────────────────────────────────────
        if has_camera and camera is not None:
            with camera_lock:
                ret, frame = camera.read()
            if not ret:
                frame = make_placeholder_frame()
                has_camera = False
        else:
            frame = make_placeholder_frame()

        # ── Run detection ──────────────────────────────────────────────────────
        detections = detector.detect(frame)

        # ── Annotate frame ────────────────────────────────────────────────────
        annotated = det_module.draw_detections(frame.copy(), detections)

        # Draw FPS counter
        fps_text = f"FPS: {current_fps:.1f}"
        cv2.putText(annotated, fps_text, (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 180), 2, cv2.LINE_AA)

        # ── Encode to JPEG base64 ─────────────────────────────────────────────
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, 75]
        _, buffer = cv2.imencode('.jpg', annotated, encode_params)
        b64 = base64.b64encode(buffer).decode('utf-8')

        latest_frame_b64 = b64
        latest_detections = detections
        frame_count += 1

        # ── Persist to storage (every 3 frames) ───────────────────────────────
        if frame_count % 3 == 0 and detections:
            threading.Thread(target=storage.record_frame,
                             args=(detections,), daemon=True).start()

        # ── Emit to all connected clients ────────────────────────────────────
        payload = {
            'frame': b64,
            'detections': [
                {'label': d['label'], 'confidence': d['confidence'],
                 'bbox': d['bbox']}
                for d in detections
            ],
            'fps': round(current_fps, 1),
            'frame_count': frame_count,
        }
        socketio.emit('frame', payload)

        # ── FPS calculation ───────────────────────────────────────────────────
        elapsed = time.time() - loop_start
        fps_tracker.append(elapsed)
        if len(fps_tracker) > 30:
            fps_tracker.pop(0)
        if fps_tracker:
            current_fps = 1.0 / (sum(fps_tracker) / len(fps_tracker))

        # Maintain ~24 FPS
        target_dt = 1.0 / 24.0
        sleep_t = max(0, target_dt - elapsed)
        time.sleep(sleep_t)

    print("[STREAM] Detection loop stopped")


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/status')
def api_status():
    mode = "simulation" if (detector and detector.simulation_mode) else "live"
    return jsonify({
        'status': 'running',
        'mode': mode,
        'stream_active': stream_active,
        'fps': round(current_fps, 1),
        'frames_processed': frame_count,
    })


@app.route('/api/stats')
def api_stats():
    return jsonify(storage.get_summary())


@app.route('/api/reset', methods=['POST'])
def api_reset():
    storage.reset_data()
    return jsonify({'success': True, 'message': 'Detection data cleared'})


@app.route('/api/detections/recent')
def api_recent():
    summary = storage.get_summary()
    return jsonify({
        'timeline': summary['timeline'],
        'total_counts': summary['total_counts'],
    })


@app.route('/api/export')
def api_export():
    summary = storage.get_summary()
    return jsonify(summary)


# ── Socket.IO Events ───────────────────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    print(f"[WS] Client connected: {request.sid}")
    # Send latest frame immediately on connect
    if latest_frame_b64:
        emit('frame', {
            'frame': latest_frame_b64,
            'detections': [{'label': d['label'], 'confidence': d['confidence'],
                            'bbox': d['bbox']} for d in latest_detections],
            'fps': round(current_fps, 1),
            'frame_count': frame_count,
        })


@socketio.on('disconnect')
def on_disconnect():
    print(f"[WS] Client disconnected: {request.sid}")


# ── Startup ────────────────────────────────────────────────────────────────────

def start_background_services():
    global detection_thread
    init_detector()
    detection_thread = threading.Thread(target=detection_loop, daemon=True)
    detection_thread.start()
    print("[APP] Background detection thread started")


if __name__ == '__main__':
    os.makedirs('data', exist_ok=True)
    start_background_services()

    print("\n" + "="*55)
    print("  [*] VisionAI Object Detection System")
    print("  Dashboard: http://localhost:5000")
    print("="*55 + "\n")

    socketio.run(app, host='0.0.0.0', port=5000, debug=False,
                 use_reloader=False, log_output=True,
                 allow_unsafe_werkzeug=True)
