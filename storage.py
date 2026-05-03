"""
VisionAI - Storage Layer
Handles JSON-based persistence for detection history.
"""

import json
import os
import time
from datetime import datetime
from collections import defaultdict
import threading

DATA_FILE = os.path.join('data', 'detections.json')
LOCK = threading.Lock()

# ── Schema ─────────────────────────────────────────────────────────────────────
# {
#   "total_counts": { "book": 12, "person": 45, ... },
#   "timeline": [
#     { "ts": 1714700000, "time": "2026-05-03 08:30:00",
#       "detections": [{"label": "book", "confidence": 0.85, "bbox": [...]}, ...] }
#   ],
#   "session_start": "2026-05-03 08:30:00",
#   "frames_processed": 1200
# }


def _load_raw():
    if not os.path.exists(DATA_FILE):
        return _empty_store()
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return _empty_store()


def _empty_store():
    return {
        'total_counts': {},
        'timeline': [],
        'session_start': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'frames_processed': 0,
    }


def _save(data):
    os.makedirs('data', exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)


# ── Public API ──────────────────────────────────────────────────────────────────

def record_frame(detections: list):
    """Persist a batch of detections from one frame."""
    with LOCK:
        data = _load_raw()
        data['frames_processed'] = data.get('frames_processed', 0) + 1

        # Update total counts
        counts = data.setdefault('total_counts', {})
        for det in detections:
            label = det['label']
            counts[label] = counts.get(label, 0) + 1

        # Append timeline entry (throttled: one per second max)
        timeline = data.setdefault('timeline', [])
        now_ts = int(time.time())
        if not timeline or timeline[-1]['ts'] != now_ts:
            snapshot = {
                'ts': now_ts,
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'detections': [
                    {'label': d['label'], 'confidence': d['confidence']}
                    for d in detections
                ],
                'count': len(detections),
            }
            timeline.append(snapshot)
            # Keep last 1 hour of timeline (3600 entries)
            if len(timeline) > 3600:
                data['timeline'] = timeline[-3600:]

        _save(data)


def get_summary():
    """Return aggregated stats for the dashboard."""
    with LOCK:
        data = _load_raw()

    counts = data.get('total_counts', {})
    timeline = data.get('timeline', [])

    # Per-minute aggregation for line chart (last 60 minutes)
    per_minute = defaultdict(lambda: defaultdict(int))
    cutoff = int(time.time()) - 3600
    for entry in timeline:
        if entry['ts'] >= cutoff:
            minute_key = datetime.fromtimestamp(entry['ts']).strftime('%H:%M')
            for det in entry.get('detections', []):
                per_minute[minute_key][det['label']] += 1

    # Sort timeline keys
    sorted_minutes = sorted(per_minute.keys())
    all_labels = sorted(counts.keys())

    line_data = {
        'labels': sorted_minutes,
        'datasets': {
            label: [per_minute[m].get(label, 0) for m in sorted_minutes]
            for label in all_labels
        }
    }

    return {
        'total_counts': counts,
        'timeline': timeline[-60:],   # last 60 seconds
        'line_data': line_data,
        'frames_processed': data.get('frames_processed', 0),
        'session_start': data.get('session_start', ''),
        'total_objects': sum(counts.values()),
    }


def reset_data():
    """Clear all stored detection data."""
    with LOCK:
        _save(_empty_store())
