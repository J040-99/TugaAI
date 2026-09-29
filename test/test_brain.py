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


def test_client_settings_nested_under_ui():
    """O frontend guarda directConnections sob settings.ui — tem de ser encontrado."""
    from open_webui.utils.brain import _user_settings_dict, direct_provider_for, resolve_model

    user = _FakeUser(
        {
            'ui': {
                'directConnections': {
                    'OPENAI_API_BASE_URLS': ['https://openrouter.ai/api/v1'],
                    'OPENAI_API_KEYS': ['sk-x'],
                    'OPENAI_API_CONFIGS': {'0': {'model_ids': ['google/gemma-4-26b-a4b-it:free']}},
                }
            }
        }
    )

    merged = _user_settings_dict(user)
    assert direct_provider_for(merged, 'google/gemma-4-26b-a4b-it:free') == (
        'https://openrouter.ai/api/v1',
        'sk-x',
    )
    # Sem catálogo de modelos no servidor → primeiro modelo da ligação do cliente
    assert resolve_model(user, 'organize', {}) == 'google/gemma-4-26b-a4b-it:free'


def test_reflection_accepts_plain_prose_when_model_skips_json():
    """Modelos pequenos/devolvem texto livre — nao pode ser deitado fora."""
    from open_webui.utils.brain import parse_reflection_payload

    prose = (
        'A base de conhecimento fala de viagens em familia e de trabalho no '
        'projeto TugaAI, com pessoas como Maria e Joao ao longo de setembro.'
    )
    payload = parse_reflection_payload(prose)
    assert payload is not None
    assert payload['memory_index'] == prose
    assert payload['insights'] == []

    # Texto demasiado curto continua a ser rejeitado
    assert parse_reflection_payload('curto demais') is None


def test_build_ask_prompt_packs_memory_stats_cards_and_question():
    from open_webui.utils.brain import build_ask_prompt

    state = {
        'memory_index': 'A base fala de viagens em familia e de trabalho.',
        'stats': {'documents': 6, 'people':2, 'places':1, 'categories': {'memory':3}},
    }
    cards = [
        {
            'filename': 'viagem.pdf',
            'brain': {'title': 'Viagem a Lisboa', 'summary': 'Fui a Lisboa com a Maria.', 'date': '2026-09-01'},
        }
    ]

    class _User:
        name = 'Mica'

    prompt = build_ask_prompt('Onde é que eu estive?', state, cards, _User())

    assert 'português de Portugal' in prompt  # lingua obrigatoria
    assert 'A base fala de viagens em familia e de trabalho.' in prompt
    assert 'documentos=6' in prompt
    assert '- [viagem.pdf] 2026-09-01 | Viagem a Lisboa — Fui a Lisboa com a Maria.' in prompt
    assert 'Onde é que eu estive?' in prompt
    # Sem fichas casadas → bloco explicito (nao vazio)
    vazia = build_ask_prompt('x', state, [], None)
    assert 'nenhuma ficha corresponde' in vazia


def test_reasoning_leak_is_rejected_and_prose_still_accepted():
    from open_webui.utils.brain import _looks_like_reasoning, parse_brain_payload, parse_reflection_payload

    leaked = ("Here's a thinking process:1. **Analyze User Request:** - "
              "**Goal:** Create a JSON object with two keys: memory_index and insights...")
    assert _looks_like_reasoning(leaked)
    assert not _looks_like_reasoning('A base de conhecimento fala de viagens e de trabalho.')

    # Nunca suja a memoria nem gera fichas a partir de pensamento vazado
    assert parse_reflection_payload(leaked) is None
    assert parse_brain_payload(leaked) is None

    # Prosa normal continua aceite (fallback)
    prosa = ('Este documento resume a materia de base de dados do2 ano com exemplos praticos '
             'de SQL, criacao de tabelas e consultas.')
    ok = parse_reflection_payload(prosa)
    assert ok is not None and 'base de dados' in ok['memory_index']


def test_sanitize_answer_strips_leaked_reasoning():
    from open_webui.utils.brain import sanitize_answer

    leakado = ("Here's a thinking process:1. Analyze the question2. Check memory\n"
               "A base de dados cria-se com CREATE TABLE e depois insere-se com INSERT.")
    limpo = sanitize_answer(leakado)
    assert limpo is not None
    assert 'thinking process' not in limpo.lower()
    assert 'CREATE TABLE' in limpo

    # So pensamento (sem resposta util) → rejeitado
    assert sanitize_answer("Here's a thinking process: only thinking here, nothing else") is None
    # Resposta normal passa intacta
    normal = 'Usa CREATE TABLE para criar a tabela e INSERT para inserir linhas.'
    assert sanitize_answer(normal) == normal
    assert sanitize_answer('') is None


def test_sanitize_handles_analysis_style_leaks():
    from open_webui.utils.brain import sanitize_answer

    # Pensamento numerado sem o marcador classico → corta e aceita a resposta
    sujo = 'Analyze User Input: ver a memoria\nCREATE TABLE cria a tabela e INSERT insere.'
    limpo = sanitize_answer(sujo)
    assert limpo is not None and 'CREATE TABLE' in limpo and 'Analyze' not in limpo

    # So pensamento mesmo depois do corte → rejeitado
    assert sanitize_answer('1. **Analyze User Input:**\nMore thinking, step by step, nothing else.') is None


def test_card_matches_by_keyword_not_only_full_phrase():
    from open_webui.utils.brain import card_matches

    cartao = {
        'filename': 'mysql-create.pdf',
        'brain': {
            'title': 'CREATE TABLE',
            'summary': 'Passos para criar uma base de dados em MySQL.',
            'tags': [],
            'entities': [],
        },
    }
    assert card_matches(cartao, q='Como cria uma base de dados?')  # token "dados"
    outro = {
        'filename': 'cozinha.pdf',
        'brain': {'title': 'Receitas', 'summary': 'Bolo de chocolate.', 'tags': [], 'entities': []},
    }
    assert not card_matches(outro, q='Como cria uma base de dados?')


def test_ask_prompt_includes_document_excerpts_for_practical_answers():
    from open_webui.utils.brain import build_ask_prompt

    prompt = build_ask_prompt(
        'Como cria uma tabela?',
        {'memory_index': 'Base de dados.', 'stats': {}},
        [],
        None,
        excerpts=[('mysql.pdf', 'CREATE TABLE alunos (id INT PRIMARY KEY, nome TEXT);')],
    )
    assert '## [mysql.pdf]' in prompt
    assert 'CREATE TABLE alunos' in prompt
    # Sem trechos → bloco explicito
    vazio = build_ask_prompt('x', {'memory_index': 'y', 'stats': {}}, [], None)
    assert 'sem trechos disponíveis' in vazio


def test_garbage_cards_are_detected_for_self_healing():
    from open_webui.utils.brain import _is_garbage_card

    # Lixos reais vistos na página /brain
    assert _is_garbage_card({'title': "Here's a thinking process:1. **Analyze the Request:**", 'summary': 'x'})
    assert _is_garbage_card(
        {'title': 'MySQL DROP TABLE', 'summary': '{ "title": "MySQL DROP TABLE", "summary": "The doc'}
    )
    assert _is_garbage_card({
        'title': 'Here inellsells whereells deepseek-ai deepseek-ai deepseek-ai',
        'summary': 'deepseek-ai deepseek-ai deepseek-ai deepseek-ai deepseek-ai',
    })
    # Fichas boas ficam intactas
    assert not _is_garbage_card(
        {'title': 'MySQL CREATE TABLE Statement', 'summary': 'Explains the CREATE TABLE syntax.'}
    )
    assert not _is_garbage_card({'title': 'Passeio a serra', 'summary': 'Subi a Serra da Estrela com a Maria.'})
