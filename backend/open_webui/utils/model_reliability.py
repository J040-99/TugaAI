"""Model trust ranking: how often each model actually answers.

Clients want to know whether their favourite model is "always busy" before
picking it.  Every chat completion outcome is recorded here and exposed as a
per-model reliability score plus a ranked list (``GET /openai/reliability``).

Scoring uses Laplace smoothing so a brand new model is not ranked first with a
single lucky success::

    score = (successes + 1) / (successes + failures + 2)

`failure` = the model could not answer (rate limited / provider outage), which
includes the moments where the automatic fallback switched to another model.

The counters are persisted to ``DATA_DIR/model_reliability.json`` (throttled,
atomic replace) so the ranking survives backend restarts.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import threading
import time
from collections import defaultdict, deque

log = logging.getLogger(__name__)

# Rolling window: outcomes older than this do not count.
RELIABILITY_WINDOW_SECONDS = 24 * 60 * 60
# Per-model cap so a hot model cannot grow the structure without bound.
RELIABILITY_MAX_EVENTS_PER_MODEL = 500
# Do not publish models with fewer observations than this (too little data).
RELIABILITY_MIN_OBSERVATIONS = 3
# Minimum seconds between two writes of the state file.
SAVE_MIN_INTERVAL_SECONDS = 5.0

_lock = threading.Lock()
# model_id -> deque[(timestamp, ok)]
_events: dict[str, deque] = defaultdict(lambda: deque(maxlen=RELIABILITY_MAX_EVENTS_PER_MODEL))
_dirty = False
_last_save = 0.0
# Resolved lazily from DATA_DIR; tests may point it somewhere else.
_state_file = None


def _state_path():
    global _state_file
    if _state_file is None:
        from open_webui.env import DATA_DIR

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _state_file = DATA_DIR / 'model_reliability.json'
    return _state_file


def _prune(bucket: deque, now: float) -> list:
    """Drop expired events (oldest first) and return the live ones."""
    while bucket and now - bucket[0][0] > RELIABILITY_WINDOW_SECONDS:
        bucket.popleft()
    return list(bucket)


def _save(force: bool = False) -> None:
    """Write the live window to disk (throttled unless ``force``)."""
    global _dirty, _last_save

    now = time.time()
    with _lock:
        if not _dirty:
            return
        if not force and now - _last_save < SAVE_MIN_INTERVAL_SECONDS:
            return
        snapshot = {}
        for model_id, bucket in _events.items():
            live = _prune(bucket, now)
            if live:
                snapshot[model_id] = [[ts, ok] for ts, ok in live]
        _dirty = False
        _last_save = now

    try:
        path = str(_state_path())
        tmp_path = f'{path}.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as handle:
            json.dump(snapshot, handle)
        os.replace(tmp_path, path)
    except Exception:
        # Losing the ranking must never break a chat request.
        log.warning('Could not persist model reliability stats', exc_info=True)


def _load() -> None:
    """Restore previously persisted events (expired ones are dropped)."""
    global _dirty

    try:
        path = str(_state_path())
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return
    except Exception:
        log.warning('Could not load model reliability stats', exc_info=True)
        return

    if not isinstance(data, dict):
        return

    now = time.time()
    with _lock:
        for model_id, events in data.items():
            if not isinstance(events, list):
                continue
            bucket = _events[str(model_id)]
            for entry in events:
                try:
                    timestamp, ok = entry
                    timestamp = float(timestamp)
                except (TypeError, ValueError):
                    continue
                if now - timestamp <= RELIABILITY_WINDOW_SECONDS:
                    bucket.append((timestamp, bool(ok)))


def _record(model_id: str, ok: bool) -> None:
    if not model_id:
        return
    now = time.time()
    global _dirty
    with _lock:
        _events[str(model_id)].append((now, ok))
        _dirty = True
    _save()


def record_success(model_id: str) -> None:
    """The model answered the request."""
    _record(model_id, True)


def record_unavailable(model_id: str) -> None:
    """The model could not answer (rate limit / provider outage / fallback)."""
    _record(model_id, False)


def get_model_stats(model_id: str) -> dict | None:
    """Stats for one model, or None when there is no live observation."""
    if not model_id:
        return None
    now = time.time()
    with _lock:
        bucket = _events.get(str(model_id))
        live = _prune(bucket, now) if bucket else []

    if not live:
        return None

    successes = sum(1 for _, ok in live if ok)
    failures = len(live) - successes
    return {
        'model': model_id,
        'successes': successes,
        'failures': failures,
        'observations': len(live),
        'score': round((successes + 1) / (len(live) + 2), 4),
        'status': 'available' if failures == 0 else ('busy' if successes else 'unavailable'),
    }


def get_ranking(limit: int | None = None, include_untested: bool = False) -> list[dict]:
    """All tracked models, best reliability first.

    Models with fewer than ``RELIABILITY_MIN_OBSERVATIONS`` live observations
    are hidden by default — the ranking should not send anyone to a model that
    was tried once five minutes ago.
    """
    now = time.time()
    with _lock:
        snapshot = {model_id: _prune(bucket, now) for model_id, bucket in list(_events.items())}

    ranking = []
    for model_id, live in snapshot.items():
        if not live:
            # Nothing inside the window: not ranked at all (even untested).
            continue
        if len(live) < RELIABILITY_MIN_OBSERVATIONS and not include_untested:
            continue

        successes = sum(1 for _, ok in live if ok)
        failures = len(live) - successes
        observations = len(live)
        ranking.append(
            {
                'model': model_id,
                'successes': successes,
                'failures': failures,
                'observations': observations,
                'score': round((successes + 1) / (observations + 2), 4),
                'status': (
                    'available' if failures == 0 else ('busy' if successes else 'unavailable')
                ),
            }
        )

    # Best score first; with equal scores, prefer the model with more evidence.
    ranking.sort(key=lambda item: (item['score'], item['observations']), reverse=True)

    if limit is not None:
        return ranking[:limit]
    return ranking


def reset() -> None:
    """Clear all observations (used by tests) and remember to persist that."""
    global _dirty
    with _lock:
        _events.clear()
        _dirty = True


# Warm the ranking on startup and flush it on a clean shutdown.
_load()
atexit.register(lambda: _save(force=True))
