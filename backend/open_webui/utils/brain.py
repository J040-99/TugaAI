"""Modo cérebro — organização automática dos ficheiros carregados.

Depois de um ficheiro ser processado (texto extraído), este módulo corre em
**background** e pede a um LLM que produza uma ficha de memória em JSON:

    título · resumo · tags · categoria · data · entidades (pessoas/lugares/temas)

O resultado fica em ``file.data['brain']`` — visível na API de ficheiros,
pesquisável e pronto para a futura página ``/brain``.

Configuração (env):
    BRAIN_ORGANIZE=true|false   (default: true)
    BRAIN_MODEL=<id do modelo>  (default: primeiro modelo disponível)

O LLM é opcional: se falhar, o ficheiro fica organizado como dantes — nunca
parte o upload.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time

log = logging.getLogger(__name__)

BRAIN_ORGANIZE_ENABLED = os.getenv('BRAIN_ORGANIZE', 'true').lower() == 'true'
BRAIN_MODEL = (os.getenv('BRAIN_MODEL') or '').strip()
BRAIN_MAX_CONTENT_CHARS = 12_000

CATEGORIES = ('memory', 'person', 'place', 'document', 'other')
ENTITY_TYPES = ('person', 'place', 'topic')

BRAIN_PROMPT_TEMPLATE = """You are the memory organiser of a personal knowledge base (a "brain").
Analyse the document below and answer with ONLY a single JSON object — no markdown, no commentary.

Keys:
  "title":    short title, max 80 characters
  "summary":  1-2 sentence summary of what this document is about
  "tags":     array of 3-8 lowercase keywords
  "category": one of "memory" | "person" | "place" | "document" | "other"
  "date":     "YYYY-MM-DD" if the document clearly refers to a specific date, otherwise null
  "entities": array of at most 10 objects {"type": "person"|"place"|"topic", "name": "..."}
              for notable people, places or topics mentioned

Write "title", "summary", "tags" and entity names in the SAME language as the document.

Document:
---
{text}
---"""


def build_prompt(text: str) -> str:
    """Prompt for *text*, truncated so we stay inside sane context limits.

    Uses ``replace`` instead of ``str.format`` because the template contains
    literal JSON braces (``{"type": ...}``) that must survive untouched.
    """
    text = (text or '').strip()
    if len(text) > BRAIN_MAX_CONTENT_CHARS:
        text = text[:BRAIN_MAX_CONTENT_CHARS] + '\n[... truncated ...]'
    return BRAIN_PROMPT_TEMPLATE.replace('{text}', text or '(empty document)')


def _clean_str(value, limit: int) -> str:
    if not isinstance(value, str):
        return ''
    return ' '.join(value.split())[:limit]


def _normalise_tags(raw_tags) -> list[str]:
    """Lista de tags: strings, minúsculas, sem duplicados, máx. 8."""
    tags: list[str] = []
    if not isinstance(raw_tags, list):
        return tags
    for tag in raw_tags[:8]:
        tag = _clean_str(str(tag), 48).lower()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def _normalise_entities(raw_entities) -> list[dict]:
    """Lista de entidades: só dicts com nome, tipo corrigido, máx. 10."""
    entities: list[dict] = []
    if not isinstance(raw_entities, list):
        return entities
    for item in raw_entities[:10]:
        if not isinstance(item, dict):
            continue
        name = _clean_str(str(item.get('name', '')), 80)
        if not name:
            continue
        entity_type = item.get('type')
        if not isinstance(entity_type, str) or entity_type not in ENTITY_TYPES:
            entity_type = 'topic'
        entities.append({'type': entity_type, 'name': name})
    return entities


def parse_brain_payload(raw) -> dict | None:
    """Extrai e valida o JSON do cérebro a partir da resposta do LLM.

    Tolerante ao mundo real: cercas ```json, texto antes/depois, chaves em
    falta, tipos errados. Devolve None quando não há nada utilizável.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None

    text = raw.strip()
    fenced = re.match(r'^```(?:json)?\s*(.*?)\s*```$', text, re.S)
    if fenced:
        text = fenced.group(1).strip()

    start, end = text.find('{'), text.rfind('}')
    if start == -1 or end <= start:
        return None

    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    title = _clean_str(data.get('title'), 120)
    summary = _clean_str(data.get('summary'), 600)
    if not title and not summary:
        return None

    tags = _normalise_tags(data.get('tags'))

    category = data.get('category')
    if not isinstance(category, str) or category not in CATEGORIES:
        category = 'other'

    date = data.get('date')
    if not isinstance(date, str) or not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
        date = None

    entities = _normalise_entities(data.get('entities'))

    return {
        'title': title or (summary[:80] if summary else 'Documento'),
        'summary': summary,
        'tags': tags,
        'category': category,
        'date': date,
        'entities': entities,
    }


def build_brain_card(file) -> dict | None:
    """Ficha de memória de um ficheiro (para a página /brain), ou None.

    Não inclui o conteúdo extraído — só os metadados organizados, para a
    lista ficar leve.
    """
    data = getattr(file, 'data', None) or {}
    brain = data.get('brain') if isinstance(data, dict) else None
    if not isinstance(brain, dict):
        return None

    return {
        'id': file.id,
        'filename': file.filename,
        'created_at': file.created_at,
        'updated_at': file.updated_at,
        'brain': {
            'title': brain.get('title') or file.filename,
            'summary': brain.get('summary') or '',
            'tags': brain.get('tags') or [],
            'category': brain.get('category') or 'other',
            'date': brain.get('date'),
            'entities': brain.get('entities') or [],
            'organized_at': brain.get('organized_at'),
            'model': brain.get('model'),
        },
    }


async def iter_brain_cards(user_id: str | None = None, page_size: int = 200):
    """Varre os ficheiros por PÁGINAS e produz só as fichas.

    O conteúdo extraído (o que ocupa memória) é descartado página a página —
    a diferença entre carregar1M de ficheiros com texto e carregar1M de
    fichinhas de ~1KB.
    """
    from open_webui.models.files import Files

    skip = 0
    while True:
        page = await Files.get_file_list(user_id=user_id, skip=skip, limit=page_size)
        if not page.items:
            return
        for file in page.items:
            card = build_brain_card(file)
            if card:
                yield card
        skip += len(page.items)
        if page.total is not None and skip >= page.total:
            return


def card_matches(card: dict, q: str = '', category: str = '') -> bool:
    """Filtro servidor: texto livre (título/resumo/tags/entidades/ficheiro) + categoria."""
    brain = card.get('brain') or {}
    cat = (category or '').strip()
    if cat and cat != 'all' and brain.get('category') != cat:
        return False

    text = (q or '').strip().lower()
    if not text:
        return True

    haystack = ' '.join(
        part
        for part in [
            brain.get('title'),
            brain.get('summary'),
            card.get('filename'),
            ' '.join(brain.get('tags') or []),
            ' '.join((entity or {}).get('name', '') for entity in brain.get('entities') or []),
        ]
        if part
    ).lower()
    return text in haystack


async def query_brain_cards(
    user_id: str | None = None,
    q: str = '',
    category: str = '',
    offset: int = 0,
    limit: int = 200,
    page_size: int = 200,
) -> dict:
    """Janela paginada de fichas com total — nunca retém mais do que a janela.

    Varre por páginas (memória limitada), aplica o filtro servidor a cada ficha
    e só guarda as fichas da janela pedida. Ordena a janela por data.
    """
    matched = 0
    items: list[dict] = []
    skip = 0

    from open_webui.models.files import Files

    while True:
        page = await Files.get_file_list(user_id=user_id, skip=skip, limit=page_size)
        if not page.items:
            break
        for file in page.items:
            card = build_brain_card(file)
            if not card or not card_matches(card, q, category):
                continue
            if matched >= offset and len(items) < limit:
                items.append(card)
            matched += 1
        skip += len(page.items)
        if page.total is not None and skip >= page.total:
            break

    items.sort(
        key=lambda card: (
            (card.get('brain') or {}).get('date') or '',
            card.get('created_at') or 0,
        ),
        reverse=True,
    )
    return {'items': items, 'total': matched, 'offset': offset, 'limit': limit}


async def organize_file(request, file_id: str, user) -> dict | None:
    """Produz a ficha de memória de um ficheiro e grava-a em ``data['brain']``."""
    if not BRAIN_ORGANIZE_ENABLED:
        return None

    # Imports tardios: evitam ciclos (utils.chat carrega os routers).
    from open_webui.models.files import Files
    from open_webui.utils.chat import generate_chat_completion

    file = await Files.get_file_by_id(file_id)
    if not file:
        return None

    content = (file.data or {}).get('content')
    if not isinstance(content, str) or len(content.strip()) < 40:
        log.debug('brain: file %s has too little content; skipping', file_id)
        return None

    models = getattr(request.app.state, 'MODELS', None) or {}
    model = BRAIN_MODEL or next(iter(models), None)
    if not model:
        log.warning('brain: no model available to organise file %s', file_id)
        return None

    form_data = {
        'model': model,
        'messages': [{'role': 'user', 'content': build_prompt(content)}],
        'stream': False,
        'temperature': 0,
        'max_tokens': 700,
    }

    try:
        res = await generate_chat_completion(
            request, form_data, user, bypass_filter=True, bypass_system_prompt=True
        )
    except Exception:
        log.warning('brain: LLM call failed for file %s', file_id, exc_info=True)
        return None

    try:
        raw = res['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError):
        log.warning('brain: unexpected LLM response for file %s: %s', file_id, res)
        return None

    payload = parse_brain_payload(raw)
    if not payload:
        log.warning('brain: could not parse organiser output for file %s', file_id)
        return None

    payload['organized_at'] = int(time.time())
    payload['model'] = model
    await Files.update_file_data_by_id(file_id, {'brain': payload})
    log.info('brain: organised file %s → "%s" [%s]', file_id, payload['title'], payload['category'])
    return payload


async def _organize_safe(request, file_id: str, user) -> None:
    try:
        await organize_file(request, file_id, user)
    except Exception:
        # O cérebro é um extra: nunca pode rebentar o upload de um ficheiro.
        log.exception('brain: background organisation failed for file %s', file_id)


def schedule_organize(request, file_id: str, user) -> None:
    """Agenda a organização sem bloquear o processamento do ficheiro."""
    if not BRAIN_ORGANIZE_ENABLED or not file_id:
        return
    try:
        asyncio.create_task(_organize_safe(request, file_id, user))
    except RuntimeError:
        # Sem event loop a correr (ex.: contexto de teste) — ignorar.
        log.debug('brain: no running event loop; skipping organisation of %s', file_id)


##########################################
# Raciocínio periódico ("reflexão")
#
# De hora a hora (configurável) o cérebro relê tudo o que organizou e produz:
#   • stats actuais (documentos, pessoas, lugares, categorias, tags)
#   • um "índice de memória" — o que a IA sabe sobre ti, em parágrafo
#   • insights — ligações entre documentos (tema, resumo, documentos ligados)
# O estado fica em DATA_DIR/brain_reflection.json e é servido por
# GET /api/v1/files/brain/state. Env: BRAIN_REFLECT_INTERVAL (minutos;0=off).
##########################################

BRAIN_REFLECT_INTERVAL = float(os.getenv('BRAIN_REFLECT_INTERVAL', '60'))
BRAIN_REFLECT_MIN_CARDS = 2
BRAIN_REFLECT_MAX_CARDS = 150
BRAIN_REFLECTION_FILENAME = 'brain_reflection.json'
BRAIN_REFLECTION_MAX_INSIGHTS = 6

REFLECTION_PROMPT_TEMPLATE = """You are the long-term memory of a personal knowledge base (a "brain").
Below is the current inventory of organised documents (date | category | title — summary; entities).

Reflect on it and answer with ONLY a single JSON object (no markdown, no commentary):

  "memory_index": 1-3 paragraph description of everything this person's knowledge base is about —
                  who/what appears often, main themes, timeline. Written in the SAME language as
                  the documents (Portuguese if they are in Portuguese).
  "insights":     array of 1 to {max_insights} objects connecting documents that belong together:
                    {"topic": "short theme", "summary": "1-2 sentences on the connection",
                     "related": ["exact document titles that connect"]}

Be concrete and useful; never invent documents that are not listed.

Inventory:
---
{inventory}
---
"""

_reflection_file = None


def _reflection_path():
    global _reflection_file
    if _reflection_file is None:
        from open_webui.env import DATA_DIR

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _reflection_file = DATA_DIR / BRAIN_REFLECTION_FILENAME
    return _reflection_file


def load_reflection() -> dict:
    """Última reflexão persistida (dict vazio se ainda não houver)."""
    try:
        with open(str(_reflection_path()), encoding='utf-8') as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        log.warning('brain: could not load reflection state', exc_info=True)
        return {}


def save_reflection(state: dict) -> None:
    """Grava a reflexão de forma atómica; nunca levanta exceção."""
    try:
        path = str(_reflection_path())
        tmp_path = f'{path}.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as handle:
            json.dump(state, handle, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception:
        log.warning('brain: could not persist reflection state', exc_info=True)


def empty_stats() -> dict:
    """Contadores a zero — pensados para serem actualizados em streaming."""
    return {
        'documents': 0,
        '_people': set(),
        '_places': set(),
        '_entities': {},
        '_tags': {},
        'categories': {},
    }


def add_card_to_stats(stats: dict, card: dict) -> None:
    """Actualiza os contadores com uma ficha (memória constante por *valor*)."""
    brain = card.get('brain') or {}
    category = brain.get('category') or 'other'
    stats['categories'][category] = stats['categories'].get(category, 0) + 1
    stats['documents'] += 1

    for entity in brain.get('entities') or []:
        name, etype = entity.get('name'), entity.get('type') or 'topic'
        if not name:
            continue
        key = (etype, name)
        stats['_entities'][key] = stats['_entities'].get(key, 0) + 1
        if etype == 'person':
            stats['_people'].add(name)
        elif etype == 'place':
            stats['_places'].add(name)

    for tag in brain.get('tags') or []:
        stats['_tags'][tag] = stats['_tags'].get(tag, 0) + 1


def finalise_stats(stats: dict) -> dict:
    """Converte os contadores internos na forma pública (listas ordenadas)."""
    top_entities = sorted(
        ({'type': t, 'name': n, 'count': c} for (t, n), c in stats['_entities'].items()),
        key=lambda item: (-item['count'], item['name']),
    )
    top_tags = sorted(
        ({'name': name, 'count': count} for name, count in stats['_tags'].items()),
        key=lambda item: (-item['count'], item['name']),
    )
    return {
        'documents': stats['documents'],
        'people': len(stats['_people']),
        'places': len(stats['_places']),
        'tags': len(stats['_tags']),
        'categories': dict(sorted(stats['categories'].items(), key=lambda kv: -kv[1])),
        'top_entities': top_entities[:12],
        'top_tags': top_tags[:20],
    }


def reflection_stats(cards) -> dict:
    """Estrutura determinística (sem LLM) a partir das fichas."""
    stats = empty_stats()
    for card in cards:
        add_card_to_stats(stats, card)
    return finalise_stats(stats)


def build_reflection_prompt(cards: list[dict]) -> str:
    """Inventário legível das fichas para o LLM refletir."""
    lines = []
    for index, card in enumerate(cards[:BRAIN_REFLECT_MAX_CARDS], start=1):
        brain = card.get('brain') or {}
        date = brain.get('date') or '?'
        title = brain.get('title') or card.get('filename') or 'sem título'
        summary = (brain.get('summary') or '')[:200]
        entities = ', '.join(
            f"{e.get('name')} ({e.get('type', 'topic')})" for e in (brain.get('entities') or [])[:6]
        )
        line = f"{index}. {date} | {brain.get('category', 'other')} | {title}"
        if summary:
            line += f' — {summary}'
        if entities:
            line += f' | {entities}'
        lines.append(line)

    inventory = '\n'.join(lines) if lines else '(empty)'
    return REFLECTION_PROMPT_TEMPLATE.replace('{inventory}', inventory).replace(
        '{max_insights}', str(BRAIN_REFLECTION_MAX_INSIGHTS)
    )


def _normalise_insights(raw_insights) -> list[dict]:
    """Insights: dicts com tema+resumo, related sem duplicados, máx. N."""
    insights: list[dict] = []
    if not isinstance(raw_insights, list):
        return insights
    for item in raw_insights[:BRAIN_REFLECTION_MAX_INSIGHTS]:
        if not isinstance(item, dict):
            continue
        topic = _clean_str(str(item.get('topic', '')), 120)
        summary = _clean_str(str(item.get('summary', '')), 500)
        if not topic or not summary:
            continue
        related: list[str] = []
        raw_related = item.get('related')
        if isinstance(raw_related, list):
            for title in raw_related[:8]:
                title = _clean_str(str(title), 120)
                if title and title not in related:
                    related.append(title)
        insights.append({'topic': topic, 'summary': summary, 'related': related})
    return insights


def parse_reflection_payload(raw) -> dict | None:
    """Valida a reflexão do LLM (índice + insights), tolerando ruído."""
    if not isinstance(raw, str) or not raw.strip():
        return None

    text = raw.strip()
    fenced = re.match(r'^```(?:json)?\s*(.*?)\s*```$', text, re.S)
    if fenced:
        text = fenced.group(1).strip()

    start, end = text.find('{'), text.rfind('}')
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    memory_index = _clean_str(data.get('memory_index'), 4000)
    insights = _normalise_insights(data.get('insights'))

    if not memory_index and not insights:
        return None
    return {'memory_index': memory_index, 'insights': insights}


def _reflection_request(app):
    """Request sintético para poder reutilizar o pipeline normal do chat."""
    from starlette.requests import Request

    scope = {
        'type': 'http',
        'asgi': {'version': '3.0', 'spec_version': '2.3'},
        'http_version': '1.1',
        'method': 'POST',
        'scheme': 'http',
        'path': '/brain/reflection',
        'raw_path': b'/brain/reflection',
        'query_string': b'',
        'root_path': '',
        'headers': [],
        'client': ('127.0.0.1', 0),
        'server': ('127.0.0.1', 80),
        'app': app,
        'state': {},
    }
    return Request(scope)


async def _brain_system_user():
    """Primeiro utilizador disponível (admin preferido) para a chamada interna."""
    try:
        from open_webui.models.users import Users

        for query in ({'role': 'admin'}, None):
            result = await (Users.get_users(filter=query, limit=1) if query else Users.get_users(limit=1))
            if isinstance(result, dict):
                for value in result.values():
                    if isinstance(value, list) and value:
                        return value[0]
            elif isinstance(result, list) and result:
                return result[0]
    except Exception:
        log.warning('brain: could not load a user for reflection', exc_info=True)
    return None


async def _streaming_stats() -> dict:
    """Stats de todos os ficheiros com ficha, em memória só de contadores."""
    stats = empty_stats()
    async for card in iter_brain_cards():
        add_card_to_stats(stats, card)
    return finalise_stats(stats)


async def _recent_cards(limit: int) -> list[dict]:
    """As *limit* fichas mais recentes, com min-heap (memória constante)."""
    import heapq

    def _sort_key(card: dict):
        return ((card.get('brain') or {}).get('date') or '', card.get('created_at') or 0)

    heap: list = []
    sequence = 0
    async for card in iter_brain_cards():
        key = _sort_key(card)
        if len(heap) < limit:
            heapq.heappush(heap, (key, sequence, card))
        elif key > heap[0][0]:
            heapq.heapreplace(heap, (key, sequence, card))
        sequence += 1
    return [card for _, _, card in sorted(heap, key=lambda item: item[0], reverse=True)]


async def run_reflection(app) -> dict:
    """Um ciclo de raciocínio: stats → (opcional) insights via LLM → estado."""
    from open_webui.utils.chat import generate_chat_completion

    # Passo 1: stats em streaming — só contadores na memória, nunca as fichas
    # e muito menos o conteúdo dos ficheiros.
    stats = await _streaming_stats()

    # Passo 2: só as BRAIN_REFLECT_MAX_CARDS fichas mais recentes entram no prompt.
    cards = await _recent_cards(BRAIN_REFLECT_MAX_CARDS)
    state = {
        'updated_at': int(time.time()),
        'stats': stats,
        'memory_index': '',
        'insights': [],
        'model': None,
    }

    if len(cards) < BRAIN_REFLECT_MIN_CARDS:
        save_reflection(state)
        log.info('brain: reflection skipped — only %d card(s)', len(cards))
        return state

    models = getattr(app.state, 'MODELS', None) or {}
    model = BRAIN_MODEL or next(iter(models), None)
    user = await _brain_system_user() if model else None

    if model and user:
        form_data = {
            'model': model,
            'messages': [{'role': 'user', 'content': build_reflection_prompt(cards)}],
            'stream': False,
            'temperature': 0.2,
            'max_tokens': 1100,
        }
        try:
            res = await generate_chat_completion(
                _reflection_request(app), form_data, user, bypass_filter=True, bypass_system_prompt=True
            )
            raw = res['choices'][0]['message']['content']
            payload = parse_reflection_payload(raw)
            if payload:
                state['memory_index'] = payload['memory_index']
                state['insights'] = payload['insights']
                state['model'] = model
        except Exception:
            log.warning('brain: reflection LLM call failed', exc_info=True)
    elif not model:
        log.debug('brain: no model available for reflection')

    save_reflection(state)
    log.info(
        'brain: reflection done — %d documents, %d insights',
        stats['documents'],
        len(state['insights']),
    )
    return state


async def brain_reflection_loop(app) -> None:
    """Loop infinito (arrancado no startup) — nunca morre por uma exceção."""
    if BRAIN_REFLECT_INTERVAL <= 0:
        log.info('brain: periodic reflection disabled (BRAIN_REFLECT_INTERVAL=0)')
        return

    interval = BRAIN_REFLECT_INTERVAL * 60
    log.info('brain: periodic reflection started — every %.0f minutes', BRAIN_REFLECT_INTERVAL)
    while True:
        await asyncio.sleep(interval)
        try:
            await run_reflection(app)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('brain: reflection cycle failed')


##########################################
# Visão — o cérebro descreve imagens
#
# Sem motor de OCR configurado, uma imagem não tem texto para indexar.
# Em vez de a guardar "muda", pedimos a um modelo de visão uma descrição em
# português — é esse texto que passa a ser pesquisável no Knowledge.
# Env: BRAIN_VISION_MODEL (default: primeiro modelo disponível)
##########################################

BRAIN_VISION_MODEL = (os.getenv('BRAIN_VISION_MODEL') or '').strip()
BRAIN_VISION_MAX_BYTES = 15 * 1024 * 1024
BRAIN_VISION_MAX_SIDE = 1536

VISION_PROMPT = (
    'Descreve esta imagem em português de Portugal, em 2 a 4 frases, para a '
    'guardar numa base de conhecimento pessoal e a poder pesquisar depois. '
    'Transcreve qualquer texto visível e menciona pessoas, lugares, objetos e '
    'contexto se os reconheceres. Responde apenas com a descrição, sem '
    'preâmbulos nem formatação.'
)


def _image_data_uri(path: str, content_type: str | None = None) -> str | None:
    """Data URI pronto para um modelo de visão (redimensionado e comprimido)."""
    import base64
    import io as _io

    from PIL import Image

    try:
        with open(path, 'rb') as handle:
            raw = handle.read()
    except OSError:
        return None

    if len(raw) > BRAIN_VISION_MAX_BYTES:
        log.info('brain: image too big for vision (%d bytes); skipping description', len(raw))
        return None

    try:
        with Image.open(_io.BytesIO(raw)) as image:
            image = image.convert('RGB')
            image.thumbnail((BRAIN_VISION_MAX_SIDE, BRAIN_VISION_MAX_SIDE))
            buffer = _io.BytesIO()
            image.save(buffer, format='JPEG', quality=85)
            encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
        return f'data:image/jpeg;base64,{encoded}'
    except Exception:
        # PIL não conseguiu processar — tenta o original pelo MIME.
        if not content_type:
            return None
        try:
            return f'data:{content_type};base64,{base64.b64encode(raw).decode("ascii")}'
        except Exception:
            return None


async def describe_image(request, file_path: str, content_type: str | None, user) -> str | None:
    """Descrição em texto de uma imagem, via modelo de visão (None se falhar)."""
    if not BRAIN_ORGANIZE_ENABLED:
        return None

    from open_webui.storage.provider import Storage
    from open_webui.utils.chat import generate_chat_completion

    models = getattr(request.app.state, 'MODELS', None) or {}
    model = BRAIN_VISION_MODEL or next(iter(models), None)
    if not model:
        log.debug('brain: no model available to describe images')
        return None

    resolved = await asyncio.to_thread(Storage.get_file, file_path)
    data_uri = await asyncio.to_thread(_image_data_uri, resolved, content_type)
    if not data_uri:
        return None

    form_data = {
        'model': model,
        'messages': [
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': VISION_PROMPT},
                    {'type': 'image_url', 'image_url': {'url': data_uri}},
                ],
            }
        ],
        'stream': False,
        'temperature': 0.2,
        'max_tokens': 600,
    }

    try:
        res = await generate_chat_completion(
            request, form_data, user, bypass_filter=True, bypass_system_prompt=True
        )
        text = res['choices'][0]['message']['content']
    except Exception:
        log.warning('brain: vision description failed for %s', file_path, exc_info=True)
        return None

    text = (text or '').strip()
    if len(text) < 20:
        return None

    log.info('brain: image described by %s (%d chars)', model, len(text))
    return text
