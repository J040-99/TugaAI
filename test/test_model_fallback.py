"""Automatic switch to an available model: candidate selection and the note.

When the requested model cannot answer (HTTP 429/502/503/504 after the bounded
retries), the route switches to the nearest available model **on the same
connection** and prefixes the answer with a note saying which model replied.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest  # noqa: F401

# Isolate the app data dir BEFORE importing open_webui so the test never runs
# alembic migrations against the real webui.db.
os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='tugaai-test-data-'))
os.environ.setdefault('WEBUI_SECRET_KEY', 'unit-test-secret-key')

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from open_webui.routers import openai as openai_router  # noqa: E402
from open_webui.utils.json_codec import JSONCodec  # noqa: E402

FREE_CATALOGUE = {
    'google/gemma-4-26b-a4b-it:free': {'urlIdx': 0},
    'google/gemma-3-27b-it:free': {'urlIdx': 0},
    'google/gemini-2.0-flash-exp:free': {'urlIdx': 0},
    'meta-llama/llama-3.3-70b-instruct:free': {'urlIdx': 0},
    'openai/gpt-4o-mini': {'urlIdx': 0},
    'mistralai/mistral-small-3.1-24b-instruct:free': {'urlIdx': 1},
}


def test_trigger_statuses_are_provider_outages_only():
    assert 429 in openai_router.FALLBACK_TRIGGER_STATUSES  # rate limit
    assert {502, 503, 504} <= set(openai_router.FALLBACK_TRIGGER_STATUSES)  # gateway down
    # Request/auth errors: another model would fail the same way.
    assert 400 not in openai_router.FALLBACK_TRIGGER_STATUSES
    assert 401 not in openai_router.FALLBACK_TRIGGER_STATUSES


def test_prefers_sibling_from_same_namespace():
    candidates = openai_router.list_fallback_models('google/gemma-4-26b-a4b-it:free', FREE_CATALOGUE)
    assert candidates, candidates
    # Nearest first: same namespace before any other free model.
    assert candidates[0].startswith('google/')
    assert candidates[0] != 'google/gemma-4-26b-a4b-it:free'
    assert 'mistralai/mistral-small-3.1-24b-instruct:free' not in candidates  # other connection


def test_falls_back_for_paid_models_too():
    # A paid model that is down switches to the nearest available one instead
    # of failing the turn (the visible note tells the user what happened).
    picked = openai_router.pick_fallback_model('openai/gpt-4o-mini', FREE_CATALOGUE)
    assert picked is not None
    assert picked != 'openai/gpt-4o-mini'


def test_same_connection_only():
    # Request known on urlIdx 1 → candidates must stay on urlIdx 1.
    candidates = openai_router.list_fallback_models(
        'mistralai/mistral-small-3.1-24b-instruct:free', FREE_CATALOGUE
    )
    assert candidates == []


def test_returns_none_when_no_fallback_applies():
    assert openai_router.pick_fallback_model(None, FREE_CATALOGUE) is None
    assert openai_router.pick_fallback_model('gemma-4', FREE_CATALOGUE) is None  # no namespace
    # Unknown model: never guess which key/url would be used.
    assert openai_router.pick_fallback_model('google/other:free', {}) is None
    assert openai_router.pick_fallback_model('google/other:free', FREE_CATALOGUE) is None


def test_candidate_list_is_capped():
    catalogue = {f'google/model-{i}:free': {'urlIdx': 0} for i in range(10)}
    catalogue['google/the-requested:free'] = {'urlIdx': 0}
    candidates = openai_router.list_fallback_models('google/the-requested:free', catalogue)
    assert len(candidates) == openai_router.FALLBACK_MAX_CANDIDATES


class _User:
    def __init__(self, language):
        self.language = language


def test_note_is_localized_by_user_language():
    pt = openai_router.build_fallback_note('google/a:free', 'google/b:free', _User('pt-PT'))
    en = openai_router.build_fallback_note('google/a:free', 'google/b:free', _User('en-US'))
    none = openai_router.build_fallback_note('google/a:free', 'google/b:free', None)

    assert pt.startswith('> **Nota:**')
    assert '`google/a:free`' in pt and '`google/b:free`' in pt
    assert en.startswith('> **Note:**')
    assert none.startswith('> **Note:**')  # default when unknown


async def _collect(stream):
    return [chunk async for chunk in stream]


def test_note_is_injected_into_first_content_delta_only():
    async def upstream():
        yield 'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
        yield 'data: {"choices":[{"delta":{"content":"Olá"}}]}\n\n'
        yield 'data: {"choices":[{"delta":{"content":" mundo"}}]}\n\n'
        yield 'data: [DONE]\n\n'

    chunks = asyncio.run(_collect(openai_router.inject_note_into_stream('NOTA', upstream())))

    # Role-only chunk untouched.
    assert '"role":"assistant"' in chunks[0] or '"role": "assistant"' in chunks[0]

    first_content = JSONCodec.loads(chunks[1][len('data: '):].strip())
    assert first_content['choices'][0]['delta']['content'] == 'NOTA\n\nOlá'

    # Second content chunk and terminator untouched.
    second_content = JSONCodec.loads(chunks[2][len('data: '):].strip())
    assert second_content['choices'][0]['delta']['content'] == ' mundo'
    assert chunks[3].strip() == 'data: [DONE]'
