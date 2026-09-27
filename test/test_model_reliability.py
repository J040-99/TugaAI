"""Model trust ranking: scores, ordering, rolling window and persistence."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Isolate the data dir BEFORE importing open_webui: the module persists its
# counters to DATA_DIR and tests must never touch the real ones.
os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='tugaai-test-data-'))
os.environ.setdefault('WEBUI_SECRET_KEY', 'unit-test-secret-key')

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from open_webui.utils import model_reliability as reliability  # noqa: E402


def setup_function(_function):
    reliability.reset()


def test_scores_use_laplace_smoothing():
    reliability.record_success('model-a')  # 1/1 but barely any evidence
    stats = reliability.get_model_stats('model-a')
    assert stats['successes'] == 1 and stats['failures'] == 0
    # (1 + 1) / (1 + 2) = 0.6667 — a single lucky success is not a "10.0".
    assert stats['score'] == 0.6667


def test_ranking_puts_reliable_models_first():
    for _ in range(9):
        reliability.record_success('reliable-model')
    for _ in range(9):
        reliability.record_unavailable('busy-model')

    ranking = reliability.get_ranking()
    assert [item['model'] for item in ranking][:2] == ['reliable-model', 'busy-model']
    assert ranking[0]['score'] > ranking[1]['score']
    assert ranking[0]['status'] == 'available'
    assert ranking[1]['status'] == 'unavailable'


def test_status_distinguishes_busy_from_broken():
    for _ in range(5):
        reliability.record_success('flaky')
    for _ in range(3):
        reliability.record_unavailable('flaky')

    stats = reliability.get_model_stats('flaky')
    assert stats['status'] == 'busy'  # answers sometimes → "ocupado"
    assert stats['observations'] == 8


def test_models_with_too_little_data_are_hidden():
    reliability.record_success('newcomer')  # 1 observation < minimum of 3
    assert reliability.get_ranking() == []
    # ...but callers can opt in to see it.
    untested = reliability.get_ranking(include_untested=True)
    assert [item['model'] for item in untested] == ['newcomer']


def test_observations_expire_after_the_window():
    bucket = reliability._events['old-model']
    now = time.time()
    bucket.append((now - reliability.RELIABILITY_WINDOW_SECONDS - 60, True))  # expired
    bucket.append((now - 10, True))  # live

    stats = reliability.get_model_stats('old-model')
    assert stats['observations'] == 1

    # All events expired → no stats at all.
    bucket.clear()
    bucket.append((now - reliability.RELIABILITY_WINDOW_SECONDS - 60, True))
    assert reliability.get_model_stats('old-model') is None
    assert reliability.get_ranking(include_untested=True) == []


def test_ranking_can_be_limited():
    for index in range(5):
        for _ in range(5):
            reliability.record_success(f'model-{index}')
    assert len(reliability.get_ranking(limit=2)) == 2


def test_empty_model_id_is_ignored():
    reliability.record_success('')
    reliability.record_unavailable(None)
    assert reliability.get_ranking(include_untested=True) == []


def test_stats_survive_a_restart(tmp_path):
    """Counters are persisted to disk and restored on the next startup."""
    original_file = reliability._state_file
    state_file = tmp_path / 'model_reliability.json'
    try:
        reliability._state_file = state_file
        reliability.reset()

        for _ in range(6):
            reliability.record_success('keeper-model')
        for _ in range(2):
            reliability.record_unavailable('keeper-model')
        reliability._save(force=True)

        assert state_file.exists(), 'state file was not written'

        # Simulate a backend restart.
        reliability.reset()
        assert reliability.get_model_stats('keeper-model') is None

        reliability._load()
        stats = reliability.get_model_stats('keeper-model')
        assert stats is not None
        assert stats['observations'] == 8
        assert stats['successes'] == 6 and stats['failures'] == 2
        assert stats['status'] == 'busy'
    finally:
        reliability._state_file = original_file
        reliability.reset()


def test_expired_events_are_not_restored(tmp_path):
    original_file = reliability._state_file
    state_file = tmp_path / 'stale.json'
    try:
        reliability._state_file = state_file
        reliability.reset()

        stale = time.time() - reliability.RELIABILITY_WINDOW_SECONDS - 3600
        state_file.write_text(
            json.dumps({'stale-model': [[stale, True], [stale + 1, False]]}),
            encoding='utf-8',
        )
        reliability._load()
        assert reliability.get_model_stats('stale-model') is None
        assert reliability.get_ranking(include_untested=True) == []
    finally:
        reliability._state_file = original_file
        reliability.reset()


def test_corrupt_state_file_is_tolerated(tmp_path):
    original_file = reliability._state_file
    state_file = tmp_path / 'corrupt.json'
    try:
        reliability._state_file = state_file
        reliability.reset()
        state_file.write_text('{not json at all', encoding='utf-8')

        reliability._load()  # must not raise
        assert reliability.get_ranking(include_untested=True) == []
    finally:
        reliability._state_file = original_file
        reliability.reset()
