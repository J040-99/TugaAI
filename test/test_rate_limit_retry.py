"""Tests for the HTTP 429 retry used by the OpenAI-compatible chat route.

The upstream backend (OpenRouter's `:free` models) rejects chat requests with
429 when its shared pool is saturated; ``_request_with_rate_limit_retry`` must
replay them a bounded number of times before surfacing the error.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Isolate the app data dir BEFORE importing open_webui so the test never runs
# alembic migrations against the real webui.db.
os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='tugaai-test-data-'))
os.environ.setdefault('WEBUI_SECRET_KEY', 'unit-test-secret-key')

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from open_webui.routers import openai as openai_router  # noqa: E402


class FakeResponse:
    def __init__(self, status, headers=None):
        self.status = status
        self.headers = headers or {'Content-Type': 'application/json'}
        self.closed = False

    def close(self):
        self.closed = True


class FakeSession:
    """Session that answers a scripted sequence of HTTP status codes."""

    def __init__(self, statuses, headers=None):
        self.statuses = list(statuses)
        self.headers = headers
        self.calls = 0
        self.responses = []

    async def request(self, **kwargs):
        self.calls += 1
        resp = FakeResponse(self.statuses.pop(0), self.headers)
        self.responses.append(resp)
        return resp


def _call(session):
    return asyncio.run(
        openai_router._request_with_rate_limit_retry(
            session,
            url='http://example.invalid/chat/completions',
            payload='{}',
            headers={},
            cookies=None,
            timeout=None,
            model_id='google/gemma-4-31b-it:free',
        )
    )


def test_retry_delay_honours_retry_after():
    assert openai_router._rate_limit_retry_delay({'Retry-After': '2'}, 0) == 2.0


def test_retry_delay_is_exponential_with_jitter():
    delay_attempt0 = openai_router._rate_limit_retry_delay({}, 0)
    delay_attempt1 = openai_router._rate_limit_retry_delay({}, 1)
    assert 1.0 <= delay_attempt0 <= 1.5
    assert 2.0 <= delay_attempt1 <= 3.0


def test_retry_delay_is_capped():
    assert openai_router._rate_limit_retry_delay({'Retry-After': '9999'}, 0) == openai_router.RATE_LIMIT_RETRY_MAX_DELAY


def test_retry_delay_falls_back_on_invalid_header():
    assert openai_router._rate_limit_retry_delay({'Retry-After': 'abc'}, 0) >= 1.0


def test_retries_until_success():
    session = FakeSession([429, 429, 200], headers={'Retry-After': '0'})
    response = _call(session)
    assert session.calls == 3
    assert response.status == 200
    # Interim responses must be released so pooled connections are not leaked.
    assert all(resp.closed for resp in session.responses[:2])
    assert not session.responses[2].closed


def test_stops_after_max_attempts_and_returns_last_429():
    session = FakeSession([429] * 10, headers={'Retry-After': '0'})
    response = _call(session)
    assert session.calls == openai_router.RATE_LIMIT_MAX_ATTEMPTS
    assert response.status == 429
    assert all(resp.closed for resp in session.responses[:-1])


def test_successful_request_is_not_retried():
    session = FakeSession([200])
    response = _call(session)
    assert session.calls == 1
    assert response.status == 200


@pytest.mark.parametrize('status', [400, 401, 500])
def test_non_rate_limit_errors_are_not_retried(status):
    session = FakeSession([status])
    response = _call(session)
    assert session.calls == 1
    assert response.status == status
