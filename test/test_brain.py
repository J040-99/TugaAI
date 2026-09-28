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
