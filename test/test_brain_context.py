"""Modo cérebro — contexto do completion e nota de conversa (write-back).

Cobre:
  • build_brain_context (bloco pronto a injectar, sem LLM, nunca exceção);
  • learn_from_conversation (nota-ficheiro com Pergunta/Resposta + filename).
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='tugaai-test-data-'))
os.environ.setdefault('WEBUI_SECRET_KEY', 'unit-test-secret-key')

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))


def _card(filename, title, summary, category='document', date='2026-01-01'):
    return {
        'id': f'id-{filename}',
        'filename': filename,
        'created_at': 1,
        'brain': {'title': title, 'summary': summary, 'category': category, 'date': date},
    }


def test_build_brain_context_formats_injectable_block(monkeypatch):
    import open_webui.utils.brain as brain

    async def fake_cards(question, limit=6):
        assert question == 'Como criar tabelas em MySQL?'
        assert limit == 6
        return [
            _card('mysql.pdf', 'MySQL CREATE TABLE', 'Passos para criar tabelas.', 'document'),
            _card('receitas.pdf', 'Receitas', 'Bolo de chocolate.', 'other'),
        ]

    async def fake_excerpts(matched, limit=4):
        return [('mysql.pdf', 'CREATE TABLE alunos (id INT PRIMARY KEY, nome TEXT);')]

    monkeypatch.setattr(
        brain,
        'load_reflection',
        lambda: {
            'memory_index': 'Base sobre MySQL e viagens à serra.',
            'insights': [
                {'topic': 'MySQL', 'summary': 'Documentos sobre criar tabelas e consultas.', 'related': []}
            ],
            'stats': {'documents': 2},
        },
    )
    monkeypatch.setattr(brain, 'find_cards_for_question', fake_cards)
    monkeypatch.setattr(brain, '_load_excerpts', fake_excerpts)

    ctx = asyncio.run(brain.build_brain_context('Como criar tabelas em MySQL?'))

    assert set(ctx.keys()) >= {'context', 'sources', 'memory_index'}
    assert ctx['memory_index'] == 'Base sobre MySQL e viagens à serra.'
    assert ctx['sources'] == ['mysql.pdf', 'receitas.pdf']
    assert 'CONHECIMENTO PESSOAL DO UTILIZADOR' in ctx['context']
    assert 'Índice de memória:' in ctx['context']
    assert 'Base sobre MySQL e viagens à serra.' in ctx['context']
    assert '- MySQL: Documentos sobre criar tabelas e consultas.' in ctx['context']
    assert 'Documentos relevantes:' in ctx['context']
    assert '- MySQL CREATE TABLE [document] (mysql.pdf): Passos para criar tabelas.' in ctx['context']
    assert 'Excertos:' in ctx['context']
    assert '=== mysql.pdf ===' in ctx['context']
    assert 'CREATE TABLE alunos' in ctx['context']


def test_build_brain_context_without_data_returns_partial_dict(monkeypatch):
    import open_webui.utils.brain as brain

    async def no_cards(question, limit=6):
        return []

    async def no_excerpts(matched, limit=4):
        return []

    monkeypatch.setattr(brain, 'load_reflection', lambda: {})
    monkeypatch.setattr(brain, 'find_cards_for_question', no_cards)
    monkeypatch.setattr(brain, '_load_excerpts', no_excerpts)

    ctx = asyncio.run(brain.build_brain_context('pergunta sem memória'))
    assert set(ctx.keys()) >= {'context', 'sources', 'memory_index'}
    assert ctx['sources'] == []
    assert ctx['memory_index'] == ''
    assert ctx['context'] == ''  # sem nada útil → sem bloco para injectar


def test_build_brain_context_never_raises_on_failures(monkeypatch):
    import open_webui.utils.brain as brain

    async def exploding_cards(question, limit=6):
        raise RuntimeError('base de dados indisponível')

    async def exploding_excerpts(matched, limit=4):
        raise RuntimeError('storage em baixo')

    monkeypatch.setattr(
        brain, 'load_reflection', lambda: (_ for _ in ()).throw(RuntimeError('reflection corrompida'))
    )
    monkeypatch.setattr(brain, 'find_cards_for_question', exploding_cards)
    monkeypatch.setattr(brain, '_load_excerpts', exploding_excerpts)

    ctx = asyncio.run(brain.build_brain_context('qualquer pergunta'))
    assert set(ctx.keys()) >= {'context', 'sources', 'memory_index'}
    assert ctx == {'context': '', 'sources': [], 'memory_index': ''}


def test_build_brain_context_falls_back_to_recent_cards(monkeypatch):
    import open_webui.utils.brain as brain

    async def no_matches(question, limit=6):
        return []

    recent = [_card('antigo.pdf', 'Nota antiga', 'Memória antiga do utilizador.')]

    async def fake_recent(limit):
        assert limit == 6
        return recent

    async def fake_excerpts(matched, limit=4):
        return []

    monkeypatch.setattr(brain, 'load_reflection', lambda: {'memory_index': 'idx'})
    monkeypatch.setattr(brain, 'find_cards_for_question', no_matches)
    monkeypatch.setattr(brain, '_recent_cards', fake_recent)
    monkeypatch.setattr(brain, '_load_excerpts', fake_excerpts)

    ctx = asyncio.run(brain.build_brain_context('sem correspondências'))
    assert ctx['sources'] == ['antigo.pdf']
    assert 'Nota antiga' in ctx['context']


def _install_fake_files(monkeypatch, capture: dict):
    from open_webui.models import files as files_model

    async def fake_insert(user_id, form_data, db=None):
        capture['user_id'] = user_id
        capture['form'] = form_data
        return SimpleNamespace(id=form_data.id, filename=form_data.filename)

    def fake_upload(fileobj, filename, tags):
        capture['uploaded'] = filename
        return fileobj.read(), f'uploads/{filename}'

    monkeypatch.setattr(files_model.Files, 'insert_new_file', fake_insert)
    monkeypatch.setattr('open_webui.storage.provider.Storage.upload_file', fake_upload)


def test_learn_from_conversation_creates_note_file(monkeypatch):
    import open_webui.utils.brain as brain

    capture: dict = {}
    _install_fake_files(monkeypatch, capture)

    scheduled = {'organize': [], 'reflection': []}
    monkeypatch.setattr(
        brain, 'schedule_organize', lambda request, file_id, user: scheduled['organize'].append(file_id)
    )
    monkeypatch.setattr(brain, 'schedule_reflection', lambda app: scheduled['reflection'].append(app))

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(MODELS={})))
    user = SimpleNamespace(id='user-1')

    filename = asyncio.run(
        brain.learn_from_conversation(
            user,
            'Como criar tabelas em MySQL?',
            'Usa CREATE TABLE seguido do nome da tabela e das colunas; confirma com DESCRIBE.',
            sources=['mysql.pdf'],
            request=request,
        )
    )

    assert filename is not None and filename.startswith('conversa-cerebro-') and filename.endswith('.txt')
    assert capture['user_id'] == 'user-1'
    form = capture['form']
    assert form.filename == filename
    assert form.path == f'uploads/{filename}'
    assert form.data['content'].startswith('# Conversa com o cérebro — ')
    assert '**Pergunta:** Como criar tabelas em MySQL?' in form.data['content']
    assert '**Resposta:** Usa CREATE TABLE' in form.data['content']
    assert '**Fontes citadas:** mysql.pdf' in form.data['content']
    assert form.meta['name'] == filename
    assert form.meta['size'] == len(form.data['content'].encode('utf-8'))

    # Ficha brain + reflexão agendadas em background
    assert scheduled['organize'] == [form.id]
    assert scheduled['reflection'] == [request.app]


def test_learn_from_conversation_short_inputs_return_none(monkeypatch):
    import open_webui.utils.brain as brain

    capture: dict = {}
    _install_fake_files(monkeypatch, capture)
    user = SimpleNamespace(id='user-1')

    # Resposta curta (< 50) → None, sem inserir ficheiro
    assert (
        asyncio.run(
            brain.learn_from_conversation(
                user, 'Como criar tabelas em MySQL?', 'CREATE TABLE.'
            )
        )
        is None
    )
    # Pergunta curta (< 10) → None
    assert (
        asyncio.run(
            brain.learn_from_conversation(
                user, 'Curta?', 'Resposta longa o suficiente para passar a validação do cérebro.'
            )
        )
        is None
    )
    assert 'form' not in capture


def test_learn_from_conversation_never_raises(monkeypatch):
    import open_webui.utils.brain as brain

    async def exploding_insert(user_id, form_data, db=None):
        raise RuntimeError('bd em baixo')

    from open_webui.models import files as files_model

    monkeypatch.setattr(files_model.Files, 'insert_new_file', exploding_insert)
    user = SimpleNamespace(id='user-1')

    filename = asyncio.run(
        brain.learn_from_conversation(
            user,
            'Pergunta suficientemente longa para o cérebro aceitar?',
            'Resposta também suficientemente longa para passar a validação mínima do aprendizado.',
        )
    )
    assert filename is None  # nunca exceção para cima
