"""Modo cérebro — aprendizagens (write-back) e contexto do chat normal.

Cobre:
  • persistência/dedupe/cap das learnings (DATA_DIR/brain_learnings.json);
  • distill_learning (LLM a devolver JSON útil, vazio ou a falhar).
(O contexto do completion e a nota de conversa estão em test_brain_context.py.)
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='tugaai-test-data-'))
os.environ.setdefault('WEBUI_SECRET_KEY', 'unit-test-secret-key')

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))


def _fake_request(models=None):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(MODELS=models or {'modelo': {}})))


def test_learnings_roundtrip_dedupe_and_cap(tmp_path, monkeypatch):
    import open_webui.utils.brain as brain

    monkeypatch.setattr(brain, '_learnings_file', tmp_path / 'brain_learnings.json')
    monkeypatch.setattr(brain, 'BRAIN_MODEL', '')

    assert brain.load_learnings() == []
    assert brain.recent_learnings() == []

    assert brain.store_learning('O que é MySQL?', 'MySQL guarda dados em tabelas.', 'c1', 'u1')
    assert brain.store_learning('Prefere respostas curtas?', 'Prefere respostas curtas.', 'c1', 'u1')

    items = brain.load_learnings()
    assert len(items) == 2
    # mais recente primeiro
    assert items[0]['question'] == 'Prefere respostas curtas?'
    assert items[0]['chat_id'] == 'c1' and items[0]['user_id'] == 'u1'
    assert isinstance(items[0]['ts'], int)

    # mesma pergunta normalizada (acentos/pontuação/caixa) → actualiza, não duplica
    assert brain.store_learning('o que e mysql!', 'MySQL usa SQL.', 'c1', 'u1')
    items = brain.load_learnings()
    assert len(items) == 2
    assert items[0]['question'] == 'o que e mysql!'
    assert items[0]['learning'] == 'MySQL usa SQL.'

    # aprendizagem vazia / pergunta vazia → nada guardado
    assert not brain.store_learning('Qualquer coisa?', '')
    assert not brain.store_learning('', 'aprendizagem órfã')
    assert len(brain.load_learnings()) == 2

    # cap: nunca guarda mais de BRAIN_LEARN_MAX
    for index in range(brain.BRAIN_LEARN_MAX + 10):
        assert brain.store_learning(f'pergunta {index}', f'aprendizagem {index}')
    items = brain.load_learnings()
    assert len(items) == brain.BRAIN_LEARN_MAX
    assert items[0]['question'] == f'pergunta {brain.BRAIN_LEARN_MAX + 9}'

    # recent_learnings devolve texto (não dicts) e respeita o limite
    recent = brain.recent_learnings(3)
    assert len(recent) == 3
    assert all(isinstance(text, str) and text for text in recent)

    # nunca exceção: ficheiro corrompido
    (tmp_path / 'brain_learnings.json').write_text('{corrupt', encoding='utf-8')
    assert brain.load_learnings() == []


def test_learnings_save_never_raises(tmp_path, monkeypatch):
    import open_webui.utils.brain as brain

    # caminho impossível (directório como ficheiro) → 0, sem exceção
    monkeypatch.setattr(brain, '_learnings_file', tmp_path)
    assert brain.save_learnings([{'question': 'q', 'learning': 'l'}]) == 0
    assert brain.store_learning('q', 'l') is False


def test_distill_learning_parses_json_and_handles_failures(monkeypatch):
    import open_webui.utils.brain as brain

    monkeypatch.setattr(brain, 'BRAIN_MODEL', '')
    seen = {}

    async def fake_complete(request, form_data, user, model):
        seen['form_data'] = form_data
        seen['model'] = model
        return 'Aqui vai:\n```json\n{"learning": "O utilizador prefere respostas curtas."}\n```'

    monkeypatch.setattr(brain, 'complete_with_provider', fake_complete)

    learning = asyncio.run(
        brain.distill_learning(_fake_request(), 'Pergunta?', 'Resposta longa do assistente.')
    )
    assert learning == 'O utilizador prefere respostas curtas.'
    assert seen['model'] == 'modelo'
    assert seen['form_data']['max_tokens'] == 600
    assert seen['form_data']['stream'] is False
    assert 'português de Portugal' in seen['form_data']['messages'][0]['content']
    assert 'Pergunta?' in seen['form_data']['messages'][0]['content']

    # nada de novo → '' (falso, mas não é falha)
    monkeypatch.setattr(
        brain, 'complete_with_provider', lambda *args, **kwargs: _async_none()
    )
    assert asyncio.run(brain.distill_learning(_fake_request(), 'Olá?', 'Olá!')) == ''

    # resposta não-JSON / lixo → '' (não polui a memória)
    monkeypatch.setattr(
        brain, 'complete_with_provider', lambda *args, **kwargs: _async_value('sem json aqui')
    )
    assert asyncio.run(brain.distill_learning(_fake_request(), 'P?', 'A')) == ''

    # falha do LLM → None
    async def exploding(*args, **kwargs):
        raise RuntimeError('provider em baixo')

    monkeypatch.setattr(brain, 'complete_with_provider', exploding)
    assert asyncio.run(brain.distill_learning(_fake_request(), 'P?', 'A')) is None

    # sem modelo → None
    assert asyncio.run(brain.distill_learning(_fake_request(models={}), 'P?', 'A')) is None

    # sem pergunta/resposta → nem tenta
    assert asyncio.run(brain.distill_learning(_fake_request(), '', 'A')) is None


def _async_value(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner()


def _async_none():
    async def _inner(*args, **kwargs):
        return None

    return _inner()


def test_ask_prompt_includes_recent_learnings():
    from open_webui.utils.brain import build_ask_prompt

    prompt = build_ask_prompt(
        'O que sei de mim?',
        {'memory_index': 'idx', 'stats': {}},
        [],
        None,
        learnings=['Prefere respostas curtas.', 'Trabalha no TugaAI.'],
    )
    assert '### Aprendizagens recentes de conversas' in prompt
    assert '- Prefere respostas curtas.' in prompt
    assert '- Trabalha no TugaAI.' in prompt

    # sem aprendizagens → bloco explícito
    vazio = build_ask_prompt('x', {'memory_index': 'y', 'stats': {}}, [], None, learnings=[])
    assert 'sem aprendizagens registadas' in vazio


def test_learnings_json_file_is_newest_first_and_stable():
    """A lista gravada é newest-first e o JSON é legível (escrita atómica)."""
    import tempfile as _tempfile

    import open_webui.utils.brain as brain

    directory = _tempfile.mkdtemp(prefix='tugaai-learnings-')
    monkey_path = Path(directory) / 'brain_learnings.json'
    original = brain._learnings_file
    try:
        brain._learnings_file = monkey_path
        for index in range(3):
            brain.store_learning(f'pergunta {index}', f'aprendizagem {index}')

        data = json.loads(monkey_path.read_text(encoding='utf-8'))
        assert [item['question'] for item in data] == ['pergunta 2', 'pergunta 1', 'pergunta 0']
        assert not (Path(directory) / 'brain_learnings.json.tmp').exists()
    finally:
        brain._learnings_file = original
