import json
import os
import time
from datetime import datetime, timedelta
from config.defaults import get_default_config, SHELLMATE_DIR

CACHE_DIR = os.path.join(SHELLMATE_DIR, "cache")
CACHE_INDEX_FILE = os.path.join(CACHE_DIR, "index.faiss")
CACHE_META_FILE = os.path.join(CACHE_DIR, "metadata.json")

_embedder = None
_index = None
_metadata = []


def _get_embedder():
    global _embedder
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            config = get_default_config()
            model_name = config["cache"]["model"]
            _embedder = SentenceTransformer(model_name)
        except Exception as e:
            raise RuntimeError(f"Failed to load embedding model: {e}")
    return _embedder


def _get_index():
    global _index, _metadata
    if _index is not None:
        return _index

    import numpy as np
    import faiss

    config = get_default_config()
    os.makedirs(CACHE_DIR, exist_ok=True)

    if os.path.exists(CACHE_INDEX_FILE) and os.path.exists(CACHE_META_FILE):
        try:
            _index = faiss.read_index(CACHE_INDEX_FILE)
            with open(CACHE_META_FILE, "r") as f:
                _metadata = json.load(f)
            return _index
        except Exception:
            pass

    dim = 384
    _index = faiss.IndexFlatIP(dim)
    _metadata = []
    return _index


def _save_index():
    import faiss
    os.makedirs(CACHE_DIR, exist_ok=True)
    faiss.write_index(_index, CACHE_INDEX_FILE)
    with open(CACHE_META_FILE, "w") as f:
        json.dump(_metadata, f)


def generate_embedding(text):
    embedder = _get_embedder()
    embedding = embedder.encode([text], normalize_embeddings=True)
    return embedding[0]


def cache_lookup(command):
    global _index, _metadata

    idx = _get_index()
    if idx.ntotal == 0:
        return None

    embedding = generate_embedding(command)
    import numpy as np
    query = np.array([embedding], dtype=np.float32)

    config = get_default_config()
    threshold = config["cache"]["similarity_threshold"]
    max_entries = config["cache"]["max_entries"]
    expiration_days = config["cache"]["expiration_days"]

    scores, indices = idx.search(query, 1)
    if scores[0][0] >= threshold:
        meta_idx = int(indices[0][0])
        if meta_idx < len(_metadata):
            entry = _metadata[meta_idx]
            ts = datetime.fromisoformat(entry["timestamp"])
            if datetime.now() - ts <= timedelta(days=expiration_days):
                _prune_old_entries(expiration_days, max_entries)
                return {
                    "command": entry["command"],
                    "risk": entry.get("risk", entry.get("severity")),
                    "confidence": entry.get("confidence", 0.0),
                    "explanation": entry.get("explanation", entry.get("message", "")),
                    "alternatives": entry.get("alternatives", []),
                    "timestamp": entry["timestamp"],
                    "cached": True,
                }

    return None


def cache_store(command, result):
    global _index, _metadata

    idx = _get_index()
    embedding = generate_embedding(command)

    import numpy as np
    vector = np.array([embedding], dtype=np.float32)

    entry = {
        "command": command,
        "risk": result.get("risk", result.get("severity", "UNKNOWN")),
        "confidence": result.get("confidence", 0.0),
        "explanation": result.get("explanation", result.get("message", result.get("reason", ""))),
        "alternatives": result.get("alternatives", []),
        "timestamp": datetime.now().isoformat(),
    }

    idx.add(vector)
    _metadata.append(entry)
    _save_index()

    config = get_default_config()
    _prune_old_entries(config["cache"]["expiration_days"], config["cache"]["max_entries"])


def _prune_old_entries(expiration_days, max_entries):
    global _index, _metadata
    if not _metadata:
        return

    now = datetime.now()
    cutoff = now - timedelta(days=expiration_days)
    valid_indices = []

    for i, entry in enumerate(_metadata):
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts > cutoff:
                valid_indices.append(i)
        except (ValueError, KeyError):
            pass

    valid_indices.sort()

    if len(valid_indices) > max_entries:
        valid_indices = valid_indices[-max_entries:]

    if len(valid_indices) < len(_metadata):
        _rebuild_index(valid_indices)


def _rebuild_index(valid_indices):
    global _index, _metadata
    import numpy as np
    import faiss

    if not valid_indices:
        dim = 384
        _index = faiss.IndexFlatIP(dim)
        _metadata = []
        _save_index()
        return

    embedder = _get_embedder()
    valid_entries = [_metadata[i] for i in valid_indices]
    commands = [e["command"] for e in valid_entries]
    embeddings = embedder.encode(commands, normalize_embeddings=True)

    dim = embeddings.shape[1]
    _index = faiss.IndexFlatIP(dim)
    _index.add(np.array(embeddings, dtype=np.float32))
    _metadata = valid_entries
    _save_index()


def clear_cache():
    global _index, _metadata
    import faiss
    import numpy as np

    config = get_default_config()
    dim = 384
    _index = faiss.IndexFlatIP(dim)
    _metadata = []

    if os.path.exists(CACHE_DIR):
        import shutil
        shutil.rmtree(CACHE_DIR)

    os.makedirs(CACHE_DIR, exist_ok=True)
    _save_index()
