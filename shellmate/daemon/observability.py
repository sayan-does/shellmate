import json
import logging
import os
import time
from datetime import datetime
from shellmate.config.defaults import SHELLMATE_DIR

logger = logging.getLogger("shellmate.observability")

METRICS_FILE = os.path.join(SHELLMATE_DIR, "metrics.json")


def track_event(event_type, data=None):
    entry = {
        "event": event_type,
        "timestamp": datetime.now().isoformat(),
        "data": data or {},
    }
    logger.debug(json.dumps(entry))
    return entry


def track_latency(stage, duration_ms):
    entry = {
        "event": "latency",
        "stage": stage,
        "duration_ms": round(duration_ms, 2),
        "timestamp": datetime.now().isoformat(),
    }
    logger.debug(json.dumps(entry))
    return entry


def update_metrics(metric_data):
    os.makedirs(os.path.dirname(METRICS_FILE), exist_ok=True)
    metrics = {}
    if os.path.exists(METRICS_FILE):
        try:
            with open(METRICS_FILE, "r") as f:
                metrics = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    for key, value in metric_data.items():
        if key not in metrics:
            metrics[key] = []
        metrics[key].append({
            "value": value,
            "timestamp": datetime.now().isoformat(),
        })
        if len(metrics[key]) > 1000:
            metrics[key] = metrics[key][-1000:]

    try:
        with open(METRICS_FILE, "w") as f:
            json.dump(metrics, f, indent=2)
    except OSError:
        pass


def get_metrics_summary():
    if not os.path.exists(METRICS_FILE):
        return {"error": "No metrics data available"}

    try:
        with open(METRICS_FILE, "r") as f:
            metrics = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"error": "Could not read metrics"}

    summary = {}
    for key, entries in metrics.items():
        if entries:
            values = [e["value"] for e in entries]
            summary[key] = {
                "count": len(values),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "avg": round(sum(values) / len(values), 2),
            }

    return summary
