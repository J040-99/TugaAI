"""Modo cérebro: construção do prompt e parsing robusto da resposta do LLM."""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='tugaai-test-data-'))
os.environ.setdefault('WEBUI_SECRET_KEY', 'unit-test-secret-key')

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from open_webui.utils.brain import (  # noqa: E402
    BRAIN_MAX_CONTENT_CHARS,
    BRAIN_PROMPT_TEMPLATE,
    build_prompt,
    parse_brain_payload,
)


def test_build_prompt_truncates_long_documents():
    huge = 'palavra ' * 5000  # >> 12k chars
    prompt = build_prompt(huge)
    # Só o documento é cortado (mais o marcador): o resto é o template.
    assert len(prompt) < BRAIN_MAX_CONTENT_CHARS + len(BRAIN_PROMPT_TEMPLATE) + 50
    assert '[... truncated ...]' in prompt
    assert prompt.rstrip().endswith('---')


def test_build_prompt_handles_empty_document():
    assert '(empty document)' in build_prompt('')


def test_parses_clean_json():
    raw = (
        '{"title": "Passeio na serra", "summary": "Subi à serra com a Maria.", '
        '"tags": ["serra", "família"], "category": "memory", "date": "2026-09-12", '
        '"entities": [{"type": "person", "name": "Maria"}, {"type": "place", "name": "Serra"}]}'
    )
    payload = parse_brain_payload(raw)
    assert payload is not None
    assert payload['title'] == 'Passeio na serra'
    assert payload['category'] == 'memory'
    assert payload['date'] == '2026-09-12'
    assert payload['entities'][0] == {'type': 'person', 'name': 'Maria'}


def test_parses_fenced_json_with_surrounding_prose():
    raw = """Claro! Aqui está o JSON:
```json
{"title": "Notas", "summary": "Reunião de equipa.", "tags": ["trabalho"]}
```
Espero que ajude!"""
    payload = parse_brain_payload(raw)
    assert payload is not None
    assert payload['title'] == 'Notas'
    assert payload['category'] == 'other'  # em falta → default
    assert payload['date'] is None


def test_rejects_garbage():
    assert parse_brain_payload('') is None
    assert parse_brain_payload(None) is None
    assert parse_brain_payload('não sei escrever json') is None
    assert parse_brain_payload('{"apenas": "sem resumo"}') is None  # sem título/resumo
    assert parse_brain_payload('{"summary": 42}') is None  # tipo errado e sem título


def test_normalises_bad_values():
    raw = (
        '{"title": "  Espaços\\n a mais  ", "summary": "ok", "tags": ["A", "a", 7, "b"], '
        '"category": "banana", "date": "amanhã", '
        '"entities": [{"type": "alien", "name": "Zork"}, {"name": ""}, "lixo"]}'
    )
    payload = parse_brain_payload(raw)
    assert payload is not None
    assert payload['title'] == 'Espaços a mais'  # colapsado
    assert payload['tags'] == ['a', '7', 'b']  # minúsculas, duplicado removido
    assert payload['category'] == 'other'  # inválido → other
    assert payload['date'] is None  # não é YYYY-MM-DD
    assert payload['entities'] == [{'type': 'topic', 'name': 'Zork'}]  # type inválido corrigido


def test_reflection_prompt_lists_inventory_without_double_braces():
    from open_webui.utils.brain import build_reflection_prompt

    cards = [
        {
            'filename': 'a.txt',
            'brain': {
                'title': 'Passeio na serra',
                'summary': 'Subi à serra com a Maria.',
                'category': 'memory',
                'date': '2026-09-12',
                'entities': [
                    {'type': 'place', 'name': 'Serra'},
                    {'type': 'person', 'name': 'Maria'},
                ],
            },
        }
    ]
    prompt = build_reflection_prompt(cards)
    assert 'Passeio na serra' in prompt
    assert 'Serra (place)' in prompt and 'Maria (person)' in prompt
    assert '{{' not in prompt  # o exemplo JSON vem com chavetas simples
    assert '"topic"' in prompt  # e o modelo vê o formato pedido


def test_parse_reflection_payload_valid_and_fenced():
    from open_webui.utils.brain import parse_reflection_payload

    raw = """Aqui vai:
```json
{"memory_index": "Base sobre viagens e família.",
 "insights": [{"topic": "Viagens", "summary": "Várias memórias de viagens.", "related": ["A", "A", "B"]}]}
```
"""
    payload = parse_reflection_payload(raw)
    assert payload is not None
    assert payload['memory_index'].startswith('Base sobre')
    assert len(payload['insights']) == 1
    assert payload['insights'][0]['related'] == ['A', 'B']  # sem duplicados

    assert parse_reflection_payload('sem json') is None
    assert parse_reflection_payload('{"memory_index": "", "insights": []}') is None


def test_reflection_stats_counts_people_places_and_tags():
    from open_webui.utils.brain import reflection_stats

    cards = [
        {
            'brain': {
                'category': 'memory',
                'tags': ['viagem', 'família'],
                'entities': [
                    {'type': 'person', 'name': 'Maria'},
                    {'type': 'place', 'name': 'Serra'},
                ],
            }
        },
        {
            'brain': {
                'category': 'person',
                'tags': ['viagem'],
                'entities': [{'type': 'person', 'name': 'Maria'}],
            }
        },
    ]
    stats = reflection_stats(cards)
    assert stats['documents'] == 2
    assert stats['people'] == 1 and stats['places'] == 1
    assert stats['categories'] == {'memory': 1, 'person': 1}
    assert stats['top_tags'][0] == {'name': 'viagem', 'count': 2}
    assert stats['top_entities'][0]['name'] == 'Maria'


def test_reflection_state_roundtrip(tmp_path):
    from open_webui.utils import brain

    original = brain._reflection_file
    state_file = tmp_path / 'brain_reflection.json'
    try:
        brain._reflection_file = state_file
        brain.save_reflection({'updated_at': 123, 'memory_index': 'idx', 'insights': []})
        assert brain.load_reflection()['memory_index'] == 'idx'

        state_file.write_text('{corrupt', encoding='utf-8')
        assert brain.load_reflection() == {}  # nunca levanta exceção
    finally:
        brain._reflection_file = original


def test_image_data_uri_downscales_to_jpeg(tmp_path):

    from open_webui.utils.brain import _image_data_uri
    from PIL import Image

    png = tmp_path / 'photo.png'
    Image.new('RGB', (3000, 2000), color=(12, 200, 90)).save(png)

    uri = _image_data_uri(str(png), 'image/png')
    assert uri is not None
    assert uri.startswith('data:image/jpeg;base64,')

    # Ficheiro inexistente → None (nunca exceção)
    assert _image_data_uri(str(tmp_path / 'missing.png'), 'image/png') is None


def test_vision_prompt_asks_for_portuguese_plain_text():
    from open_webui.utils.brain import VISION_PROMPT

    assert 'português' in VISION_PROMPT
    assert 'preâmbulos' in VISION_PROMPT  # resposta só texto, para indexar


def test_pdf_pages_render_to_data_uris(tmp_path):
    import pymupdf
    from open_webui.utils.brain import _pdf_page_data_uris

    pdf = tmp_path / 'scan.pdf'
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), 'Documento de teste')
    document.save(str(pdf))
    document.close()

    uris = _pdf_page_data_uris(str(pdf))
    assert uris, 'devia renderizar a pagina'
    assert uris[0].startswith('data:image/jpeg;base64,')

    # PDF inexistente/corrompido -> lista vazia, nunca excecao
    assert _pdf_page_data_uris(str(tmp_path / 'missing.pdf')) == []


class _FakeUser:
    def __init__(self, settings=None):
        self.settings = settings


def test_resolve_model_prefers_client_choice_per_function():
    from open_webui.utils import brain

    models = {'alpha': {}, 'beta': {}}
    user = _FakeUser({'brain': {'organize_model': 'beta', 'vision_model': 'alpha'}})

    assert brain.resolve_model(user, 'organize', models) == 'beta'
    assert brain.resolve_model(user, 'vision', models) == 'alpha'


def test_resolve_model_falls_back_to_global_defaults():
    from open_webui.utils import brain

    models = {'alpha': {}, 'beta': {}}
    # Sem escolha do cliente (ou sem utilizador) → default global.
    assert brain.resolve_model(_FakeUser(None), 'organize', models) == 'alpha'
    assert brain.resolve_model(None, 'organize', models) == 'alpha'
    assert brain.resolve_model(None, 'vision', models) == 'alpha'
    assert brain.resolve_model(None, 'organize', {}) is None


def test_resolve_model_reads_pydantic_user_settings():
    from open_webui.models.users import UserSettings
    from open_webui.utils import brain

    settings = UserSettings(brain={'organize_model': 'chosen-model'})  # extra='allow'
    user = _FakeUser(settings)
    assert brain.resolve_model(user, 'organize', {'alpha': {}}) == 'chosen-model'


def test_direct_provider_matches_model_ids_and_falls_back():
    from open_webui.utils.brain import direct_provider_for

    settings = {
        'directConnections': {
            'OPENAI_API_BASE_URLS': ['https://a.example/v1', 'https://openrouter.ai/api/v1'],
            'OPENAI_API_KEYS': ['key-a', 'key-b'],
            'OPENAI_API_CONFIGS': {
                '0': {'enable': True, 'model_ids': ['outro-modelo']},
                '1': {'enable': True, 'model_ids': ['google/gemma-4-26b-a4b-it:free']},
            },
        }
    }
    # Modelo presente na lista explícita da ligação1
    assert direct_provider_for(settings, 'google/gemma-4-26b-a4b-it:free') == (
        'https://openrouter.ai/api/v1',
        'key-b',
    )
    # Modelo fora de qualquer lista → primeira ligação ativa (genérico)
    assert direct_provider_for(settings, 'modelo-desconhecido') == ('https://a.example/v1', 'key-a')
    # Sem ligações diretas → None (usa o pool global)
    assert direct_provider_for({}, 'x') is None
    assert direct_provider_for({'directConnections': {}}, 'x') is None


def test_direct_provider_skips_disabled_connections():
    from open_webui.utils.brain import direct_provider_for

    settings = {
        'directConnections': {
            'OPENAI_API_BASE_URLS': ['https://off.example/v1', 'https://on.example/v1'],
            'OPENAI_API_KEYS': ['k0', 'k1'],
            'OPENAI_API_CONFIGS': {'0': {'enable': False}, '1': {'enable': True}},
        }
    }
    assert direct_provider_for(settings, 'qualquer') == ('https://on.example/v1', 'k1')
