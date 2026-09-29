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


def _looks_like_reasoning(text: str) -> bool:
    """Resposta que é só "pensamento" do modelo a vazar — não serve de conteúdo."""
    head = (text or '')[:400].lower()
    return bool(
        re.search(
            r'thinking process|let me (think|analyz|analys)|analy[sz]e user request|'
            r'<think|step[- ]by[- ]step|objective:.*goal:',
            head,
        )
    )


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


def _load_json_object(text: str) -> dict | None:
    """Extrai o primeiro objeto JSON válido de uma resposta de LLM.

    Usa ``JSONDecoder.raw_decode`` — ignora prosa antes/depois (típico de
    modelos de raciocínio) e, em fallback, tenta sem vírgulas finais.
    """
    start = text.find('{')
    if start == -1:
        return None

    tail = text[start:]
    decoder = json.JSONDecoder()
    for candidate in (tail, re.sub(r',(\s*[}\]])', r'\1', tail)):
        try:
            data, _ = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def parse_brain_payload(raw) -> dict | None:
    """Extrai e valida o JSON do cérebro a partir da resposta do LLM.

    Tolerante ao mundo real: cercas ```json, texto antes/depois, chaves em
    falta, tipos errados. Sem JSON aproveitável mas com texto suficiente,
    monta uma ficha mínima — melhor uma ficha simples do que nada.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None

    text = raw.strip()
    fenced = re.match(r'^```(?:json)?\s*(.*?)\s*```$', text, re.S)
    if fenced:
        text = fenced.group(1).strip()

    data = _load_json_object(text)
    if data is None:
        if _looks_like_reasoning(text):
            log.warning('brain: organiser leaked reasoning — skipping (retry next cycle)')
            return None
        prose = _clean_str(text, 600)
        if len(prose) >= 40:
            log.info('brain: organiser returned non-JSON — building a minimal card')
            first_sentence = prose.split('. ')[0]
            return {
                'title': _clean_str(first_sentence, 100) or 'Documento',
                'summary': prose,
                'tags': [],
                'category': 'document',
                'date': None,
                'entities': [],
            }
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

    file = await Files.get_file_by_id(file_id)
    if not file:
        return None

    content = (file.data or {}).get('content')
    if not isinstance(content, str) or len(content.strip()) < 40:
        log.debug('brain: file %s has too little content; skipping', file_id)
        return None

    models = getattr(request.app.state, 'MODELS', None) or {}
    model = resolve_model(user, 'organize', models)
    if not model:
        log.warning('brain: no model available to organise file %s', file_id)
        return None

    form_data = {
        'model': model,
        'messages': [{'role': 'user', 'content': build_prompt(content)}],
        'stream': False,
        'temperature': 0,
        # Modelos de raciocínio (ex.: nemotron) "pensam" antes de responder —
        # com pouco espaço o JSON sai truncado e não parseia.
        'max_tokens': 4000,
    }

    try:
        raw = await complete_with_provider(request, form_data, user, model)
    except Exception:
        log.warning('brain: LLM call failed for file %s', file_id, exc_info=True)
        return None

    if not isinstance(raw, str) or not raw.strip():
        log.warning('brain: empty completion for file %s', file_id)
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
# Ficheiros antigos (feitos antes do cérebro) organizados por ciclo:
BACKLOG_ORGANIZE_PER_CYCLE = int(os.getenv('BRAIN_BACKLOG_PER_CYCLE', '5'))
BRAIN_REFLECTION_FILENAME = 'brain_reflection.json'
BRAIN_REFLECTION_MAX_INSIGHTS = 6

REFLECTION_PROMPT_TEMPLATE = """És a memória de longo prazo de uma base de conhecimento pessoal (o "cérebro").
Abaixo está o inventário actual dos documentos organizados (data | categoria | título — resumo; entidades).

Reflecte sobre ele e responde APENAS com um único objecto JSON (sem markdown, sem comentários):

  "memory_index": descrição em1-3 parágrafos de TUDO o que esta base de conhecimento cobre —
                  quem/falas aparecem com frequência, temas principais, cronologia.
  "insights":     array de1 a {max_insights} objetos que ligam documentos que pertencem juntos:
                    {"topic": "tema curto", "summary": "1-2 frases sobre a ligação",
                     "related": ["títulos exactos dos documentos que se ligam"]}

REGRA OBRIGATÓRIO DE LÍNGUA: escreve memory_index, topic e summary SEMPRE em
português de Portugal — nunca em inglês, mesmo que o inventário esteja em inglês.

REGRA DE FORMATO: vai DIRECTO ao JSON final. NÃO escrevas o teu processo de
pensamento, nem frases como "Here's a thinking process", nem passos, nem
comentários — só o objecto JSON.

Sê concreto e útil; nunca inventes documentos que não estejam listados.

Inventário:
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
    """Grava a reflexão de forma atómica; nunca levanta exceção.

    Se um ciclo não produziu índice/insights (resposta não-JSON, provedor em
    baixo), mantém os anteriores — azar de um ciclo nunca apaga bom conteúdo.
    """
    if not state.get('memory_index') and not state.get('insights'):
        previous = load_reflection()
        if previous.get('memory_index'):
            state['memory_index'] = previous['memory_index']
            state['insights'] = previous.get('insights') or []
            state['model'] = previous.get('model')

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

    data = _load_json_object(text)
    if data is None:
        # Sem JSON: prosa util serve de índice — mas se for só o "pensamento"
        # do modelo a vazar, não suja a memória (mantém-se a anterior).
        if _looks_like_reasoning(text):
            log.warning('brain: reflection leaked reasoning — keeping previous index')
            return None
        prose = _clean_str(text, 4000)
        if len(prose) >= 40:
            log.info('brain: reflection was not JSON — using plain text as memory index')
            return {'memory_index': prose, 'insights': []}
        return None

    memory_index = _clean_str(data.get('memory_index'), 4000)
    insights = _normalise_insights(data.get('insights'))

    if not memory_index and not insights:
        # Modelos pequenos/devolvem prosa em vez de JSON: usa o texto como
        # índice de memória em vez de deitar fora a resposta.
        prose = _clean_str(text, 4000)
        if len(prose) >= 40:
            log.info('brain: reflection was not JSON — using plain text as memory index')
            return {'memory_index': prose, 'insights': []}
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


async def _organize_if_pending(file, request) -> bool:
    """Organiza um ficheiro que ainda não tem ficha. True se criou ficha."""
    from open_webui.models.users import Users

    data = file.data if isinstance(file.data, dict) else {}
    if data.get('brain'):
        return False
    content = data.get('content')
    if not isinstance(content, str) or len(content.strip()) < 40:
        return False

    owner = None
    try:
        owner = await Users.get_user_by_id(file.user_id)
    except Exception:
        owner = None
    user = owner or await _brain_system_user()
    if not user:
        return False

    result = await organize_file(request, file.id, user)
    return bool(result)


async def organize_backlog(request, limit: int = BACKLOG_ORGANIZE_PER_CYCLE) -> int:
    """Organiza ficheiros antigos ainda sem ficha do cérebro (auto-sanagem).

    Uploads feitos ANTES de o cérebro existir não passaram pela organização —
    sem ficha não entram nas estatísticas nem na reflexão. Corre no início de
    cada ciclo, com limite para nunca tornar o ciclo interminável.
    """
    from open_webui.models.files import Files

    organized = 0
    skip = 0
    while organized < limit:
        page = await Files.get_file_list(skip=skip, limit=50)
        if not page.items:
            break
        for file in page.items:
            if organized >= limit:
                break
            if await _organize_if_pending(file, request):
                organized += 1
                log.info('brain: backlog organised %d/%d — %s', organized, limit, file.filename)
        skip += len(page.items)
        if page.total is not None and skip >= page.total:
            break

    if organized:
        log.info('brain: backlog organised %d file(s) this cycle', organized)
    return organized


async def run_reflection(app) -> dict:
    """Um ciclo de raciocínio: stats → (opcional) insights via LLM → estado."""

    # Passo 0: backlog — uploads antigos sem ficha (dá material à reflexão).
    try:
        await organize_backlog(_reflection_request(app))
    except Exception:
        log.exception('brain: backlog organisation failed')

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
    user = await _brain_system_user()
    model = (
        resolve_model(user, 'organize', models) if user else (BRAIN_MODEL or next(iter(models), None))
    )

    if model and user:
        form_data = {
            'model': model,
            'messages': [{'role': 'user', 'content': build_reflection_prompt(cards)}],
            'stream': False,
            'temperature': 0.2,
            'max_tokens': 4500,  # pensamento + JSON completo (modelos de raciocínio)
        }
        try:
            raw = await complete_with_provider(_reflection_request(app), form_data, user, model)
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


##########################################
# Chat com o cérebro — "pergunta à tua memória"
#
# Monta um prompt com o índice de memória + estatísticas + fichas que
# casam com a pergunta e responde via o provedor DO CLIENTE.
##########################################

ASK_PROMPT_TEMPLATE = """És o "cérebro" pessoal do utilizador — memória de longo prazo de uma base de
conhecimento pessoal. Responde em português de Portugal, raciocinando à frente
com base APENAS no material abaixo (não inventes).

Regras:
- Se a resposta não estiver na memória, diz claramente que não te lembras disso.
- Cita os documentos relevantes pelo nome entre [ ].
- Sê directo e útil; podes ligar factos de documentos diferentes.

### Índice de memória (visão geral)
{memory_index}

### Estatísticas da base
{stats}

### Fichas relevantes
{cards}

### Pergunta do utilizador
{question}
"""


def build_ask_prompt(question: str, state: dict, cards: list[dict], user=None) -> str:
    """Prompt da conversa com o cérebro (função pura, testável)."""
    stats = (state or {}).get('stats') or {}
    stats_line = (
        f"documentos={stats.get('documents', 0)}, pessoas={stats.get('people', 0)}, "
        f"lugares={stats.get('places', 0)}, categorias={stats.get('categories', {})}"
    )
    memory_index = (state or {}).get('memory_index') or '(ainda sem índice de memória)'

    lines = []
    for card in cards[:15]:
        brain = card.get('brain') or {}
        filename = card.get('filename') or '?'
        title = brain.get('title') or filename
        summary = (brain.get('summary') or '')[:400]
        date = brain.get('date') or '?'
        line = f'- [{filename}] {date} | {title}'
        if summary:
            line += f' — {summary}'
        lines.append(line)
    cards_block = '\n'.join(lines) if lines else '(nenhuma ficha corresponde à pergunta)'

    owner = getattr(user, 'name', None) or 'o utilizador'
    return (
        ASK_PROMPT_TEMPLATE.replace('{memory_index}', memory_index)
        .replace('{stats}', stats_line)
        .replace('{cards}', cards_block)
        .replace('{question}', question.strip())
        .replace('{owner}', owner)
    )


async def answer_question(request, question: str, user) -> dict | None:
    """Resposta do cérebro a uma pergunta: contexto + provedor do cliente."""
    question = (question or '').strip()
    if not question or not BRAIN_ORGANIZE_ENABLED:
        return None

    state = load_reflection()

    # Fichas que casam com a pergunta (varrimento leve, com limite).
    matched: list[dict] = []
    async for card in iter_brain_cards():
        if card_matches(card, q=question):
            matched.append(card)
            if len(matched) >= 15:
                break

    models = getattr(request.app.state, 'MODELS', None) or {}
    model = resolve_model(user, 'organize', models)
    if not model:
        log.debug('brain: no model available to answer questions')
        return None

    prompt = build_ask_prompt(question, state, matched, user)
    form_data = {
        'model': model,
        'messages': [{'role': 'user', 'content': prompt}],
        'stream': False,
        'temperature': 0.3,
        'max_tokens': 1500,
    }

    try:
        answer = await complete_with_provider(request, form_data, user, model)
    except Exception:
        log.warning('brain: question answering failed', exc_info=True)
        return None

    if not isinstance(answer, str) or not answer.strip():
        return None

    log.info('brain: question answered by %s (%d chars)', model, len(answer))
    return {
        'answer': answer.strip(),
        'sources': [card.get('filename') for card in matched if card.get('filename')],
        'model': model,
    }


async def brain_reflection_loop(app) -> None:
    """Loop infinito (arrancado no startup) — nunca morre por uma exceção."""
    if BRAIN_REFLECT_INTERVAL <= 0:
        log.info('brain: periodic reflection disabled (BRAIN_REFLECT_INTERVAL=0)')
        return

    interval = BRAIN_REFLECT_INTERVAL * 60
    # Primeira reflexão cedo (para não esperar1h por nada), depois ao ritmo.
    first_delay = min(interval, float(os.getenv('BRAIN_REFLECT_FIRST_DELAY', '60')))
    log.info(
        'brain: periodic reflection started — first run in %.0fs, then every %.0f minutes',
        first_delay,
        BRAIN_REFLECT_INTERVAL,
    )
    delay = first_delay
    while True:
        await asyncio.sleep(delay)
        delay = interval
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


def pick_vision_model(models: dict) -> str | None:
    """Melhor modelo para descrever imagens/PDFs.

    Prioridade: BRAIN_VISION_MODEL (explícito) → primeiro modelo com
    capacidade de visão nos metadados → primeiro da lista.
    """
    if BRAIN_VISION_MODEL:
        return BRAIN_VISION_MODEL
    if not isinstance(models, dict) or not models:
        return None

    for model_id, info in models.items():
        try:
            capabilities = (((info or {}).get('info') or {}).get('meta') or {}).get('capabilities') or {}
        except AttributeError:
            capabilities = {}
        if capabilities.get('vision'):
            return model_id

    return next(iter(models), None)


def resolve_model(user, function: str, models: dict) -> str | None:
    """Modelo escolhido pelo CLIENTE para uma função do cérebro.

    Ordem: ``settings.brain.<function>_model`` (por utilizador) → env global
    (``BRAIN_MODEL`` / ``BRAIN_VISION_MODEL``) → capacidade de visão ou o
    primeiro da lista.

    Funções: ``organize`` (ficha dos ficheiros) e ``vision`` (imagens + PDFs
    ilegíveis). A reflexão é global (sem utilizador) e continua a usar o env.
    """
    settings = _user_settings_dict(user)

    brain_settings = settings.get('brain') if isinstance(settings, dict) else None
    if isinstance(brain_settings, dict):
        chosen = brain_settings.get(f'{function}_model')
        if isinstance(chosen, str) and chosen.strip():
            return chosen.strip()

    if function == 'vision':
        fallback = pick_vision_model(models)
    else:
        fallback = BRAIN_MODEL or (next(iter(models), None) if isinstance(models, dict) else None)
    if fallback:
        return fallback

    # Sem catálogo no servidor (pool desativado): usa o primeiro modelo
    # declarado na ligação direta do próprio cliente.
    direct = settings.get('directConnections') if isinstance(settings, dict) else None
    if isinstance(direct, dict):
        configs = direct.get('OPENAI_API_CONFIGS') or {}
        for index in sorted(configs.keys(), key=str):
            model_ids = (configs.get(index) or {}).get('model_ids') or []
            if model_ids:
                return model_ids[0]

    # Último recurso: modelo fixado no servidor (BRAIN_MODEL) — válido para
    # qualquer ligação que o sirva, mesmo sem catálogo.
    return BRAIN_MODEL or None


def _user_settings_dict(user) -> dict:
    """Settings do utilizador como dict (aceita UserSettings do pydantic).

    O frontend guarda as preferências pessoais sob ``ui`` (``saveSettings``),
    por isso as ligações diretas podem viver em ``settings.ui.directConnections``
    — e também no topo. Devolve um dict com ambos os níveis (topo vence).
    """
    settings = getattr(user, 'settings', None)
    if settings is None:
        settings = {}
    elif isinstance(settings, dict):
        pass
    elif hasattr(settings, 'model_dump'):
        settings = settings.model_dump()
    else:
        return {}

    if not isinstance(settings, dict):
        return {}

    ui = settings.get('ui')
    if isinstance(ui, dict):
        return {**ui, **settings}
    return settings


def direct_provider_for(settings: dict, model_id: str) -> tuple[str, str] | None:
    """(base_url, api_key) da LIGAÇÃO DIRETA do cliente que serve ``model_id``.

    Cada cliente guarda o seu provedor em ``settings.directConnections``:
    ``OPENAI_API_BASE_URLS`` / ``OPENAI_API_KEYS`` / ``OPENAI_API_CONFIGS``
    (mesmo formato do pool global). Prioriza a ligação cuja lista explícita
    ``model_ids`` contém o modelo; senão, a primeira ligação ativa.
    """
    if not isinstance(settings, dict) or not model_id:
        return None
    direct = settings.get('directConnections')
    if not isinstance(direct, dict):
        return None

    urls = direct.get('OPENAI_API_BASE_URLS') or []
    keys = direct.get('OPENAI_API_KEYS') or []
    configs = direct.get('OPENAI_API_CONFIGS') or {}

    generic = None
    for index, url in enumerate(urls):
        if not url:
            continue
        config = configs.get(str(index)) or configs.get(index) or {}
        if config.get('enable') is False:
            continue
        key = keys[index] if index < len(keys) else ''
        model_ids = config.get('model_ids') or []
        if model_id in model_ids:
            return (url, key)
        if generic is None:
            generic = (url, key)
    return generic


async def _post_chat(base_url: str, api_key: str, payload: dict) -> str | None:
    """POST direto ao provedor do cliente (sem gate de pool, sem WebSocket).

    Os pools gratuitos devolvem 429 com frequência — repetimos com backoff
    curto (3 tentativas, Retry-After respeitado) antes de desistir.
    """
    import aiohttp

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'

    delay = 1.0
    for attempt in range(3):
        try:
            # Modelos de raciocínio com documentos longos passam dos3 min —
            # margem generosa para não matar a organização a meio.
            timeout = aiohttp.ClientTimeout(total=420)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 429 and attempt < 2:
                        retry_after = response.headers.get('Retry-After')
                        wait = min(10.0, float(retry_after)) if retry_after else delay
                        log.info(
                            'brain: provider rate limited (429); retrying in %.1fs (attempt %d/3)',
                            wait,
                            attempt + 2,
                        )
                        await asyncio.sleep(wait)
                        delay *= 2
                        continue

                    if response.status >= 400:
                        body = (await response.text())[:300]
                        log.warning('brain: provider HTTP %d from %s: %s', response.status, base_url, body)
                        return None

                    data = await response.json()
                    return data['choices'][0]['message']['content']
        except Exception:
            log.warning('brain: direct provider call failed for %s', base_url, exc_info=True)
            return None
    return None


async def complete_with_provider(request, form_data: dict, user, model: str) -> str | None:
    """Completion usando o provedor DO CLIENTE; fallback para o pool global.

    1. ligação direta do cliente (settings.directConnections) → HTTP direto;
    2. pool global (generate_chat_completion) — pode estar desativado; o
       chamador trata a exceção/None.
    Devolve o texto da resposta ou None.
    """
    provider = direct_provider_for(_user_settings_dict(user), model)
    if provider:
        text = await _post_chat(provider[0], provider[1], form_data)
        if text is not None:
            log.info('brain: answered by the client provider %s', provider[0])
            return text

    from open_webui.utils.chat import generate_chat_completion

    res = await generate_chat_completion(
        request, form_data, user, bypass_filter=True, bypass_system_prompt=True
    )
    return res['choices'][0]['message']['content']

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

    models = getattr(request.app.state, 'MODELS', None) or {}
    model = resolve_model(user, 'vision', models)
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
        text = await complete_with_provider(request, form_data, user, model)
    except Exception:
        log.warning('brain: vision description failed for %s', file_path, exc_info=True)
        return None

    text = (text or '').strip()
    if len(text) < 20:
        return None

    log.info('brain: image described by %s (%d chars)', model, len(text))
    return text


##########################################
# PDFs ilegíveis — o cérebro lê as páginas
#
# Um PDF digitalizado (sem camada de texto) devolve EMPTY_CONTENT e o upload
# fica 'failed'. Com PyMuPDF renderizamos as primeiras páginas e pedimos ao
# modelo de visão que descreva o que lá está — indexa-se a descrição.
# Env: BRAIN_PDF_MAX_PAGES (default3)
##########################################

BRAIN_PDF_MAX_PAGES = int(os.getenv('BRAIN_PDF_MAX_PAGES', '3'))
BRAIN_PDF_ZOOM = 1.5  # ~108 dpi — bom equilíbrio entre detalhe e tamanho

PDF_VISION_PROMPT = (
    'Estas são as primeiras páginas de um PDF que não tem texto extraível '
    '(provavelmente digitalizado ou só com imagens). Descreve o conteúdo em '
    'português de Portugal, em 3 a 6 frases, para o guardar numa base de '
    'conhecimento pessoal: transcreve o texto visível, indica pessoas, lugares, '
    'temas e o tipo de documento. Responde apenas com a descrição, sem '
    'preâmbulos nem formatação.'
)


def _pdf_page_data_uris(path: str, max_pages: int = BRAIN_PDF_MAX_PAGES) -> list[str]:
    """Renderiza as primeiras páginas de um PDF como data URIs JPEG."""
    import base64
    import io as _io

    import pymupdf
    from PIL import Image

    uris: list[str] = []
    try:
        with pymupdf.open(path) as document:
            for index in range(min(max_pages, document.page_count)):
                page = document.load_page(index)
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(BRAIN_PDF_ZOOM, BRAIN_PDF_ZOOM))
                with Image.open(_io.BytesIO(pixmap.tobytes('png'))) as image:
                    image = image.convert('RGB')
                    buffer = _io.BytesIO()
                    image.save(buffer, format='JPEG', quality=85)
                    encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
                    uris.append(f'data:image/jpeg;base64,{encoded}')
    except Exception:
        log.warning('brain: could not render PDF pages of %s', path, exc_info=True)
        return []
    return uris


async def describe_pdf(request, file_path: str, content_type: str | None, user) -> str | None:
    """Descrição em texto das primeiras páginas de um PDF ilegível (None se falhar)."""
    if not BRAIN_ORGANIZE_ENABLED:
        return None

    from open_webui.storage.provider import Storage

    models = getattr(request.app.state, 'MODELS', None) or {}
    model = resolve_model(user, 'vision', models)
    if not model:
        log.debug('brain: no model available to describe PDFs')
        return None

    resolved = await asyncio.to_thread(Storage.get_file, file_path)
    uris = await asyncio.to_thread(_pdf_page_data_uris, resolved)
    if not uris:
        return None

    content: list[dict] = [{'type': 'text', 'text': PDF_VISION_PROMPT}]
    content.extend({'type': 'image_url', 'image_url': {'url': uri}} for uri in uris)

    form_data = {
        'model': model,
        'messages': [{'role': 'user', 'content': content}],
        'stream': False,
        'temperature': 0.2,
        'max_tokens': 900,
    }

    try:
        text = await complete_with_provider(request, form_data, user, model)
    except Exception:
        log.warning('brain: PDF page description failed for %s', file_path, exc_info=True)
        return None

    text = (text or '').strip()
    if len(text) < 20:
        return None

    log.info('brain: unreadable PDF described by %s (%d chars, %d page(s))', model, len(text), len(uris))
    return text
