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
