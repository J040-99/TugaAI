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
