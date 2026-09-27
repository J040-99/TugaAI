"""Friendly error messages must be translated into pt-PT.

``src/lib/utils/errorMessages.ts`` maps raw provider payloads (429s, upstream
failures, ...) to i18n *keys* which every surface (toast, in-chat error bubble)
runs through ``t()``.  Those keys are English source strings: if one of them is
missing from the pt-PT catalogue the UI silently falls back to English for
Portuguese users — exactly what TugaAI should never do.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ERROR_MESSAGES_TS = ROOT / 'src' / 'lib' / 'utils' / 'errorMessages.ts'
ERROR_SVELTE = ROOT / 'src' / 'lib' / 'components' / 'chat' / 'Messages' / 'Error.svelte'
PT_PT = ROOT / 'src' / 'lib' / 'i18n' / 'locales' / 'pt-PT' / 'translation.json'


def _read(path: Path) -> str:
    return open(path, encoding='utf-8').read()


def _friendly_error_keys() -> list[str]:
    """Values declared inside FRIENDLY_ERROR_KEYS in errorMessages.ts."""
    src = _read(ERROR_MESSAGES_TS)
    match = re.search(r'FRIENDLY_ERROR_KEYS\s*=\s*\{(.*?)\}\s*as const;', src, re.S)
    assert match, 'FRIENDLY_ERROR_KEYS block not found in errorMessages.ts'

    keys = []
    # Strings may be split over two lines ("key:\n\t\t'value',").
    for raw in re.findall(r":\s*'((?:[^'\\]|\\.)*)'", match.group(1), re.S):
        key = re.sub(r"'\s*'", '', raw)  # rejoin split string literals
        keys.append(key)
    return keys


def _error_surface_literal_keys() -> list[str]:
    """i18n keys passed straight to ``translate()`` in the error bubble."""
    return re.findall(r"translate\(\s*'([^']+)'\s*\)", _read(ERROR_SVELTE))


def _pt_pt_catalogue() -> dict:
    return json.loads(_read(PT_PT))


def test_friendly_error_keys_are_extracted():
    keys = _friendly_error_keys()
    # Guard against the extractor silently matching nothing.
    assert len(keys) >= 5, keys
    assert any('rate-limited' in key for key in keys)
    assert any('did not respond' in key for key in keys)


def test_pt_pt_translates_every_friendly_error_key():
    missing = [key for key in _friendly_error_keys() if key not in _pt_pt_catalogue()]
    assert not missing, f'missing pt-PT translations: {missing}'


def test_pt_pt_translates_error_surface_keys():
    catalogue = _pt_pt_catalogue()
    missing = sorted({key for key in _error_surface_literal_keys() if key not in catalogue})
    assert not missing, f'missing pt-PT translations: {missing}'


def test_pt_pt_values_are_non_empty_strings():
    catalogue = _pt_pt_catalogue()
    for key in _friendly_error_keys():
        value = catalogue[key]
        assert isinstance(value, str) and value.strip(), f'empty pt-PT value for {key!r}'


def test_backend_friendly_messages_are_translated():
    """Backend friendly strings must be valid i18n keys for the frontend."""
    sys.path.insert(0, str(ROOT / 'backend'))
    from open_webui.utils import misc

    catalogue = _pt_pt_catalogue()
    frontend_keys = set(_friendly_error_keys())

    for key in (misc.FRIENDLY_RATE_LIMIT_MESSAGE, misc.FRIENDLY_MODEL_UNAVAILABLE_MESSAGE):
        assert key in catalogue, f'missing pt-PT translation for backend message: {key!r}'
        assert key in frontend_keys, f'backend message not in FRIENDLY_ERROR_KEYS: {key!r}'


# The exact payload OpenRouter returns for a saturated free pool — as reported
# by a real incident (Python's dict repr of it ended up in the chat bubble).
OPENROUTER_429_PAYLOAD = {
    'error': {
        'message': 'Provider returned error',
        'code': 429,
        'metadata': {
            'raw': (
                'google/gemma-4-26b-a4b-it:free is temporarily rate-limited upstream. '
                'Please retry shortly, or add your own key to accumulate your rate limits: '
                'https://openrouter.ai/settings/integrations'
            ),
            'provider_name': 'Google AI Studio',
            'is_byok': False,
            'provider_error_code': '429',
            'limit_source': 'upstream_provider_shared_pool',
        },
    },
    'user_id': 'user_3BzBvJU7DMsrq9fAOuRxb6lXB0J',
}


def test_openrouter_429_payload_is_never_shown_as_python_repr():
    sys.path.insert(0, str(ROOT / 'backend'))
    from open_webui.utils.misc import error_status_from_payload, friendly_provider_error_message

    message = friendly_provider_error_message(OPENROUTER_429_PAYLOAD)

    # Friendly i18n key (localized by the frontend), not the raw payload.
    assert message in _pt_pt_catalogue()
    assert (
        message
        == 'This free model is temporarily rate-limited. Wait a minute and try again, '
        'pick another free model, or add credits / your own key on OpenRouter.'
    )
    # No Python repr, no provider internals leaking to the user.
    assert not message.startswith("{'error'")
    assert 'user_id' not in message and 'metadata' not in message
    # Status survives so callers can answer with the right HTTP code.
    assert error_status_from_payload(OPENROUTER_429_PAYLOAD) == 429


def test_unknown_payload_degrades_to_readable_message_not_repr():
    sys.path.insert(0, str(ROOT / 'backend'))
    from open_webui.utils.misc import friendly_provider_error_message

    nested = {'error': {'message': 'Something exploded', 'code': 400}}
    assert friendly_provider_error_message(nested) == 'Something exploded'
    # Strings pass through untouched.
    assert friendly_provider_error_message('boom') == 'boom'
    # Payloads with no readable message degrade to JSON (double quotes),
    # never to Python's dict repr (single quotes).
    unknown = friendly_provider_error_message({'weird': True})
    assert unknown == '{"weird": true}'
