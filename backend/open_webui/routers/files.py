import asyncio
import errno
import hashlib
import logging
import os
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import func, or_, select

from fastapi.responses import FileResponse, StreamingResponse
from open_webui.config import BYPASS_ADMIN_ACCESS_CONTROL, STORAGE_LOCAL_CACHE, STORAGE_PROVIDER, UPLOAD_DIR
from open_webui.constants import ERROR_MESSAGES
from open_webui.events import EVENTS, publish_event
from open_webui.internal.db import get_async_db_context, get_async_session
from open_webui.models.access_grants import AccessGrants
from open_webui.models.channels import Channels
from open_webui.models.chats import Chats
from open_webui.models.config import Config
from open_webui.models.files import (
    File as FileRow,  # SQLAlchemy — NÃO chamar File: isso é o File(...) do FastAPI
    FileForm,
    FileListResponse,
    FileModel,
    FileModelResponse,
    Files,
)
from open_webui.models.groups import Groups
from open_webui.models.knowledge import Knowledges
from open_webui.models.users import Users
from open_webui.retrieval.vector.async_client import ASYNC_VECTOR_DB_CLIENT
from open_webui.routers.audio import transcribe
from open_webui.routers.retrieval import ProcessFileForm, process_file
from open_webui.storage.provider import Storage
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.misc import strict_match_mime_type
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

router = APIRouter()


from open_webui.utils.access_control.files import has_access_to_file
from open_webui.utils.json_codec import JSONCodec

############################
# Upload File
# What was entrusted here was given in good faith. Let it
# be returned the same way, whole and undiminished.
############################


def _is_text_file(file_path: str, chunk_size: int = 8192) -> bool:
    """Check if a file is likely a text file by reading a chunk and decoding it.

    Tries UTF-8 first, then falls back to Latin-1 (which accepts every byte
    in 0x00–0xFF) so that legacy-encoded files from Windows environments are
    not misclassified as binary.

    This catches files whose extensions are mis-mapped by mimetypes/browsers
    (e.g. TypeScript .ts → video/mp2t) without maintaining an extension whitelist.
    """
    try:
        resolved = Storage.get_file(file_path)
        with open(resolved, 'rb') as f:
            chunk = f.read(chunk_size)
        if not chunk:
            return False
        # Null bytes are a strong indicator of binary content
        if b'\x00' in chunk:
            return False
        try:
            chunk.decode('utf-8')
        except UnicodeDecodeError:
            # Latin-1 always succeeds (every byte is valid), so this
            # effectively just means "the file has no null bytes and is
            # therefore likely text, even if not valid UTF-8".
            chunk.decode('latin-1')
        return True
    except Exception:
        return False


def _cleanup_local_cache(file_path: str) -> None:
    """Remove the local cached copy of a cloud-stored file after processing."""
    if STORAGE_LOCAL_CACHE or STORAGE_PROVIDER == 'local':
        return
    try:
        local_filename = os.path.basename(file_path)
        local_path = os.path.join(UPLOAD_DIR, local_filename)
        if os.path.isfile(local_path):
            os.remove(local_path)
            log.debug('Cleaned up local cache: %s', local_path)
    except OSError as e:
        log.warning(f'Failed to clean up local cache for {file_path}: {e}')


def _matches_configured_mime_type(supported: list[str] | str, content_type: str) -> bool:
    if isinstance(supported, str):
        supported = supported.split(',')
    supported = [item.strip() for item in (supported or []) if item.strip()]
    if not supported:
        return False
    return bool(strict_match_mime_type(supported, content_type))


def _media_supported_for_extraction(
    content_extraction_engine: str | None, supported: list[str] | str | None, content_type: str
) -> bool:
    if supported is None:
        return content_extraction_engine == 'external'
    return bool(content_extraction_engine and _matches_configured_mime_type(supported, content_type))


async def process_uploaded_file(
    request,
    file,
    file_path,
    file_item,
    file_metadata,
    user,
    db: Optional[AsyncSession] = None,
):
    async def _process_handler(db_session):
        try:
            content_type = file.content_type

            # Detect mis-labeled text files (e.g. .ts → video/mp2t)
            if content_type and content_type.startswith(('image/', 'video/')):
                if _is_text_file(file_path):
                    content_type = 'text/plain'

            stt_supported = await Config.get('audio.stt.supported_content_types', [])
            content_extraction_engine = await Config.get('rag.content_extraction_engine')
            content_extraction_supported_media_mime_types = await Config.get(
                'rag.content_extraction.supported_media_mime_types'
            )

            if content_type and strict_match_mime_type(stt_supported, content_type):
                # Audio / STT-supported files → transcribe then index
                file_path_processed = await asyncio.to_thread(Storage.get_file, file_path)
                result = await transcribe(
                    request,
                    file_path_processed,
                    file_metadata,
                    user,
                )
                await process_file(
                    request,
                    ProcessFileForm(file_id=file_item.id, content=result.get('text', '')),
                    user=user,
                    db=db_session,
                )

            elif (
                content_type
                and content_type.startswith(('image/', 'video/'))
                and not _media_supported_for_extraction(
                    content_extraction_engine, content_extraction_supported_media_mime_types, content_type
                )
            ):
                if content_type.startswith('video/'):
                    # Videos are stored as-is for downstream multimodal
                    # processing (Tools, vision models). Attempting text
                    # extraction causes "Timeout reached while detecting
                    # encoding" errors.
                    log.info('Video file detected (%s), skipping text extraction', content_type)
                    await Files.update_file_data_by_id(
                        file_item.id,
                        {'status': 'completed'},
                        db=db_session,
                    )
                else:
                    # Sem motor de OCR: em vez de falhar o upload, o cérebro
                    # descreve a imagem com um modelo de visão e indexamos a
                    # descrição — fica pesquisável no Knowledge. Se não houver
                    # modelo (ou falhar), guardamos como os vídeos.
                    description = None
                    try:
                        from open_webui.utils.brain import describe_image

                        description = await describe_image(request, file_path, content_type, user)
                    except Exception:
                        log.exception('brain: image description failed for %s', file_item.id)

                    if description:
                        log.info(
                            'Image %s described by vision model; indexing description',
                            file_item.id,
                        )
                        await process_file(
                            request,
                            ProcessFileForm(file_id=file_item.id, content=description),
                            user=user,
                            db=db_session,
                        )
                    else:
                        log.info(
                            'Image file detected (%s); storing as-is without text extraction',
                            content_type,
                        )
                        await Files.update_file_data_by_id(
                            file_item.id,
                            {'status': 'completed'},
                            db=db_session,
                        )

            else:
                # Documents, or media files explicitly enabled for the
                # configured content extraction engine.
                if not content_type:
                    log.info('File type %s is not provided, but trying to process anyway', file.content_type)
                await process_file(
                    request,
                    ProcessFileForm(file_id=file_item.id),
                    user=user,
                    db=db_session,
                )

            # Auto-link to Knowledge Collection when uploaded from one (#24807).
            # Mirrors POST /knowledge/{id}/file/add so linking doesn't depend
            # on the frontend staying connected after upload.
            knowledge_id = file_metadata.get('knowledge_id')
            if knowledge_id:
                try:
                    # Gate like POST /knowledge/{id}/file/add: a client-supplied
                    # metadata.knowledge_id must not let a non-writer attach files (CWE-862/863).
                    knowledge = await Knowledges.get_knowledge_by_id(id=knowledge_id, db=db_session)
                    can_write = bool(knowledge) and (
                        knowledge.user_id == user.id
                        or user.role == 'admin'
                        or await AccessGrants.has_access(
                            user_id=user.id,
                            resource_type='knowledge',
                            resource_id=knowledge.id,
                            permission='write',
                            db=db_session,
                        )
                    )
                    if not can_write:
                        log.warning(
                            f'Refusing to auto-link file {file_item.id} to knowledge '
                            f'{knowledge_id}: user {user.id} lacks write access'
                        )
                    else:
                        directory_id = file_metadata.get('directory_id') or None
                        if directory_id:
                            directory = await Knowledges.get_directory_by_id(directory_id, db=db_session)
                            if not directory or directory.knowledge_id != knowledge_id:
                                log.warning(
                                    'Ignoring directory %s: not a directory of knowledge %s', directory_id, knowledge_id
                                )
                                directory_id = None

                        # Keep the generic file status stream open until the
                        # KB-specific vector write and durable link both finish.
                        await Files.update_file_data_by_id(file_item.id, {'status': 'processing'}, db=db_session)
                        await process_file(
                            request,
                            ProcessFileForm(file_id=file_item.id, collection_name=knowledge_id),
                            user=user,
                            db=db_session,
                        )
                        knowledge_file = await Knowledges.add_file_to_knowledge_by_id(
                            knowledge_id=knowledge_id,
                            file_id=file_item.id,
                            user_id=user.id,
                            directory_id=directory_id,
                            db=db_session,
                        )
                        if not knowledge_file:
                            raise Exception(f'Failed to link file {file_item.id} to knowledge {knowledge_id}')
                        log.info('Linked file %s to knowledge %s', file_item.id, knowledge_id)
                except Exception as e:
                    log.warning(f'Failed to link file {file_item.id} to knowledge {knowledge_id}: {e}')
                    raise

        except Exception as e:
            error_text = str(e.detail) if hasattr(e, 'detail') else str(e)

            # PDF ilegível (digitalizado/sem texto): em vez de falhar, o
            # cérebro renderiza as páginas e pede a um modelo de visão que as
            # descreva — indexamos a descrição como texto.
            description = None
            is_pdf = (file_item.filename or '').lower().endswith('.pdf') or (
                (file.content_type or '').lower() == 'application/pdf'
            )
            if is_pdf and ERROR_MESSAGES.EMPTY_CONTENT in error_text:
                #1) OCR local primeiro — offline, barato, sem depender de
                #    nenhum modelo (páginas digitalizadas que o loader não
                #    apanhou: imagens embutidas em Form XObjects).
                try:
                    from open_webui.retrieval.loaders.pdf import ocr_pdf_text
                    from open_webui.storage.provider import Storage

                    resolved = await asyncio.to_thread(Storage.get_file, file_path)
                    description = await asyncio.to_thread(ocr_pdf_text, resolved)
                except Exception:
                    description = None
                    log.exception('brain: local PDF OCR failed for %s', file_item.id)

                #2) Só depois: modelo de visão (renderiza as páginas).
                if not description:
                    try:
                        from open_webui.utils.brain import describe_pdf

                        description = await describe_pdf(request, file_path, file.content_type, user)
                    except Exception:
                        log.exception('brain: PDF description failed for %s', file_item.id)

            if description:
                log.info(
                    'Unreadable PDF %s described by vision model; indexing description',
                    file_item.id,
                )
                try:
                    await process_file(
                        request,
                        ProcessFileForm(file_id=file_item.id, content=description),
                        user=user,
                        db=db_session,
                    )
                except Exception:
                    log.exception('brain: indexing PDF description failed for %s', file_item.id)
                    description = None

            if not description:
                log.error(f'Error processing file: {file_item.id}')
                await Files.update_file_data_by_id(
                    file_item.id,
                    {
                        'status': 'failed',
                        'error': error_text,
                    },
                    db=db_session,
                )

    try:
        if db:
            await _process_handler(db)
        else:
            async with get_async_db_context() as db_session:
                await _process_handler(db_session)
    finally:
        _cleanup_local_cache(file_path)


@router.post('/', response_model=FileModelResponse)
async def upload_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    metadata: Optional[dict | str] = Form(None),
    process: bool = Query(True),
    process_in_background: bool = Query(True),
    user=Depends(get_verified_user),
    db: AsyncSession = Depends(get_async_session),
):
    result = await upload_file_handler(
        request,
        file=file,
        metadata=metadata,
        process=process,
        process_in_background=process_in_background,
        user=user,
        background_tasks=background_tasks,
        db=db,
    )

    if isinstance(result, dict):
        result_id = result.get('id')
        result_filename = result.get('filename')
        result_meta = result.get('meta') or {}
    else:
        result_id = result.id
        result_filename = result.filename
        result_meta = result.meta or {}

    result_content_type = (
        result_meta.get('content_type') if isinstance(result_meta, dict) else getattr(result_meta, 'content_type', None)
    )
    await publish_event(
        request,
        EVENTS.FILE_UPLOADED,
        actor=user,
        subject_id=result_id,
        data={'filename': result_filename, 'content_type': result_content_type},
    )
    return result


async def upload_file_handler(
    request: Request,
    file: UploadFile = File(...),
    metadata: Optional[dict | str] = Form(None),
    process: bool = Query(True),
    process_in_background: bool = Query(True),
    user=Depends(get_verified_user),
    background_tasks: Optional[BackgroundTasks] = None,
    db: Optional[AsyncSession] = None,
):
    log.info('file.content_type: %s %s', file.content_type, process)

    if isinstance(metadata, str):
        try:
            metadata = JSONCodec.loads(metadata)
        except JSONCodec.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT('Invalid metadata format'),
            )
    file_metadata = metadata if metadata else {}

    try:
        unsanitized_filename = file.filename
        filename = os.path.basename(unsanitized_filename)

        file_extension = os.path.splitext(filename)[1]
        # Remove the leading dot from the file extension and lowercase it
        file_extension = file_extension[1:].lower() if file_extension else ''

        allowed_file_extensions = await Config.get('rag.file.allowed_extensions')
        if process and allowed_file_extensions:
            allowed_file_extensions = [ext for ext in allowed_file_extensions if ext]

            if file_extension not in allowed_file_extensions:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT(f'File type {file_extension} is not allowed'),
                )

        # Prefer readable storage names for admins, but fall back if the filesystem rejects it.
        id = str(uuid.uuid4())
        name = filename
        filename = f'{id}_{filename}'
        tags = {
            'OpenWebUI-User-Email': user.email,
            'OpenWebUI-User-Id': user.id,
            'OpenWebUI-User-Name': user.name,
            'OpenWebUI-File-Id': id,
        }
        try:
            contents, file_path = await asyncio.to_thread(Storage.upload_file, file.file, filename, tags)
        except OSError as e:
            if e.errno != errno.ENAMETOOLONG:
                log.exception(e)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT(e.strerror or 'Error uploading file'),
                )

            file.file.seek(0)
            filename = f'{id}.{file_extension}' if file_extension else id
            try:
                contents, file_path = await asyncio.to_thread(Storage.upload_file, file.file, filename, tags)
            except OSError as e:
                log.exception(e)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT(e.strerror or 'Error uploading file'),
                )
        max_size = await Config.get('rag.file.max_size')
        if max_size and len(contents) > int(max_size) * 1024 * 1024:
            await asyncio.to_thread(Storage.delete_file, file_path)
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=ERROR_MESSAGES.FILE_TOO_LARGE(size=f'{max_size} MB'),
            )

        # SHA-256 of raw uploaded bytes for incremental sync diffing.
        # If the client pre-computed and sent file_hash, use that.
        file_hash = file_metadata.get('file_hash') or await asyncio.to_thread(
            lambda: hashlib.sha256(contents).hexdigest()
        )

        # Deduplicação no upload: mesmo utilizador + mesmo hash → reutiliza o
        # ficheiro existente em vez de criar outra cópia (p. ex. uploads repetidos
        # do mesmo PDF). O blob recém-escrito é removido; o processamento usa o
        # caminho do ficheiro já existente.
        existing = await Files.get_file_by_user_and_hash(user.id, file_hash, db=db)
        if existing:
            try:
                await asyncio.to_thread(Storage.delete_file, file_path)
            except Exception:
                log.debug('dedupe: blob não removido para %s', file_hash, exc_info=True)
            log.info('upload deduplicated: %s -> existing file %s', name, existing.id)
            file_item = existing
            file_path = existing.path
        else:
            file_item = await Files.insert_new_file(
                user.id,
                FileForm(
                    **{
                        'id': id,
                        'filename': name,
                        'path': file_path,
                        'data': {
                            **({'status': 'pending'} if process else {}),
                        },
                        'meta': {
                            'name': name,
                            'content_type': (file.content_type if isinstance(file.content_type, str) else None),
                            'size': len(contents),
                            'file_hash': file_hash,
                            'data': file_metadata,
                        },
                    }
                ),
                db=db,
            )

        if 'channel_id' in file_metadata:
            try:
                channel = await Channels.get_channel_by_id_and_user_id(
                    file_metadata['channel_id'], user.id, db=db
                )
                if channel:
                    await Channels.add_file_to_channel_by_id(channel.id, file_item.id, user.id, db=db)
            except Exception:
                log.warning('channel link failed for %s', file_item.id, exc_info=True)

        if process:
            if background_tasks and process_in_background:
                background_tasks.add_task(
                    process_uploaded_file,
                    request,
                    file,
                    file_path,
                    file_item,
                    file_metadata,
                    user,
                )
                return {'status': True, **file_item.model_dump()}
            else:
                await process_uploaded_file(
                    request,
                    file,
                    file_path,
                    file_item,
                    file_metadata,
                    user,
                    db=db,
                )
                return {'status': True, **file_item.model_dump()}
        else:
            if file_item:
                return file_item
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT('Error uploading file'),
                )

    except HTTPException as e:
        raise e
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                ERROR_MESSAGES.EMPTY_CONTENT
                if isinstance(e, ValueError) and e.args == (ERROR_MESSAGES.EMPTY_CONTENT,)
                else ERROR_MESSAGES.DEFAULT('Error uploading file')
            ),
        )


############################
# List Files
############################


PAGE_SIZE = 50


@router.get('/', response_model=FileListResponse)
async def list_files(
    user=Depends(get_verified_user),
    page: int = Query(1, ge=1, description='Page number (1-indexed)'),
    content: bool = Query(True),
    db: AsyncSession = Depends(get_async_session),
):
    skip = (page - 1) * PAGE_SIZE
    user_id = None if (user.role == 'admin' and BYPASS_ADMIN_ACCESS_CONTROL) else user.id

    result = await Files.get_file_list(user_id=user_id, skip=skip, limit=PAGE_SIZE, db=db)

    if not content:
        for file in result.items:
            if file.data and 'content' in file.data:
                del file.data['content']

    return result


############################
# Brain (Modo Cérebro)
############################


class BrainListResponse(BaseModel):
    items: list[dict] = []
    total: int = 0
    page: int = 1
    limit: int = 20


@router.get('/brain/state', response_model=dict)
async def get_brain_state(user=Depends(get_verified_user)):
    """Última reflexão periódica do cérebro (stats, índice de memória, insights).

    Inclui as últimas ``learnings`` (aprendizagens guardadas no write-back
    dos turnos em modo cérebro) para a página /brain.
    """
    from open_webui.utils.brain import load_reflection, recent_learnings

    state = load_reflection()
    if not isinstance(state, dict):
        state = {}
    try:
        state['learnings'] = recent_learnings()
    except Exception:
        state['learnings'] = []
    return state


@router.get('/brain', response_model=BrainListResponse)
async def list_brain_cards(
    user=Depends(get_verified_user),
    page: int = Query(1, ge=1, description='Page number (1-indexed)'),
    limit: int = Query(20, ge=1, le=100, description='Items per page'),
    q: str = Query('', description='Search in title and summary'),
    category: str = Query('all', description='Filter by category'),
    db: AsyncSession = Depends(get_async_session),
):
    """Fichas de memória organizadas pelo cérebro — paginadas e pesquisáveis.

    Filtra e pagina DIRECTAMENTE na base de dados (JSON extract): nunca carrega
    os conteúdos dos ficheiros para a memória — é o que permite crescer para
    grandes volumes.
    """
    from open_webui.utils.brain import build_brain_card

    user_id = None if (user.role == 'admin' and BYPASS_ADMIN_ACCESS_CONTROL) else user.id

    # Apenas ficheiros com data.brain, filtrados por acesso
    stmt = select(FileRow).filter(func.json_extract(FileRow.data, '$.brain').isnot(None))
    if user_id:
        stmt = stmt.filter(FileRow.user_id == user_id)

    if q.strip():
        like = f'%{q.strip()}%'
        stmt = stmt.filter(
            or_(
                FileRow.filename.like(like),
                func.json_extract(FileRow.data, '$.brain.title').like(like),
                func.json_extract(FileRow.data, '$.brain.summary').like(like),
                # tags e entidades são arrays JSON — o LIKE encontra texto lá dentro.
                func.json_extract(FileRow.data, '$.brain.tags').like(like),
                func.json_extract(FileRow.data, '$.brain.entities').like(like),
            )
        )

    if category and category != 'all':
        stmt = stmt.filter(func.json_extract(FileRow.data, '$.brain.category') == category)

    # Ordenação: data declarada (brain.date), depois created_at
    stmt = stmt.order_by(
        func.json_extract(FileRow.data, '$.brain.date').desc().nullslast(),
        FileRow.created_at.desc(),
    )

    # Contagem total (antes da paginação)
    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar_one()

    # Página
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()

    items = [card for card in (build_brain_card(row) for row in rows) if card]
    return BrainListResponse(items=items, total=total, page=page, limit=limit)


############################
# Search Files
############################


class BrainAskForm(BaseModel):
    question: str


@router.post('/brain/ask', response_model=dict)
async def ask_brain(request: Request, form_data: BrainAskForm, user=Depends(get_verified_user)):
    """Chat com o cérebro: responde a partir do índice de memória + fichas."""
    from open_webui.utils.brain import answer_question

    result = await answer_question(request, form_data.question, user)
    if not result:
        raise HTTPException(
            status_code=503, detail='O cérebro não está disponível de momento. Tenta outra vez.'
        )
    return result


@router.get('/brain/context', response_model=dict)
async def get_brain_context(
    question: str = Query(..., min_length=1, description='Pergunta do utilizador'),
    limit: int = Query(6, ge=1, le=20, description='Máximo de fichas relevantes'),
    user=Depends(get_verified_user),
):
    """Contexto do cérebro para injectar no completion do chat (modo cérebro).

    Devolve ``{context, sources, memory_index}`` — ``context`` é um bloco
    pronto a injectar no pedido de completion. Nunca falha: em erro devolve
    dict parcial (o chat segue sem contexto).
    """
    from open_webui.utils.brain import build_brain_context

    try:
        return await build_brain_context(question, limit=limit)
    except Exception:
        log.warning('brain: context endpoint failed', exc_info=True)
        return {'context': '', 'sources': [], 'memory_index': ''}


class BrainLearnForm(BaseModel):
    question: str
    answer: str
    sources: list[str] = []


@router.post('/brain/learn', response_model=dict)
async def learn_brain(request: Request, form_data: BrainLearnForm, user=Depends(get_verified_user)):
    """Write-back do modo cérebro: a conversa torna-se uma nota indexável.

    Validação: pergunta ≥ 10 caracteres e resposta ≥ 50 caracteres (senão 400).
    A ficha brain é criada em background; a nota fica visível no gestor.
    """
    from open_webui.utils.brain import learn_from_conversation

    question = (form_data.question or '').strip()
    answer = (form_data.answer or '').strip()
    if len(question) < 10 or len(answer) < 50:
        raise HTTPException(
            status_code=400,
            detail='Pergunta (mín. 10 caracteres) e resposta (mín. 50 caracteres) obrigatórias.',
        )

    try:
        filename = await learn_from_conversation(
            user, question, answer, form_data.sources or [], request
        )
    except Exception:
        log.warning('brain: learn endpoint failed', exc_info=True)
        filename = None

    if not filename:
        raise HTTPException(
            status_code=503, detail='Não foi possível guardar a conversa no cérebro. Tenta outra vez.'
        )
    return {'status': True, 'filename': filename}


class BrainCardForm(BaseModel):
    title: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    category: str | None = None
    date: str | None = None


def _require_brain_access(file, user) -> None:
    """Só o dono (ou admin) mexe nas fichas/ficheiros do cérebro."""
    if file.user_id != user.id and user.role != 'admin':
        raise HTTPException(status_code=403, detail='Sem permissão para este ficheiro.')


@router.put('/brain/{id}/card', response_model=dict)
async def update_brain_card(id: str, form_data: BrainCardForm, user=Depends(get_verified_user)):
    """Gestor: editar a ficha do cérebro (título, resumo, tags, categoria, data)."""
    import time as _time

    file = await Files.get_file_by_id(id)
    if not file:
        raise HTTPException(status_code=404, detail='Ficheiro não encontrado.')
    _require_brain_access(file, user)

    brain = dict(file.data.get('brain')) if isinstance(file.data, dict) and file.data.get('brain') else {}
    brain.update(form_data.model_dump(exclude_unset=True))
    brain['edited_at'] = int(_time.time())
    updated = await Files.update_file_data_by_id(id, {'brain': brain})
    return (updated.data or {}).get('brain') or brain


@router.post('/brain/{id}/reorganize', response_model=dict)
async def reorganize_brain_file(id: str, request: Request, user=Depends(get_verified_user)):
    """Gestor: reprocessa a ficha do cérebro de um ficheiro (reorganizar)."""
    from open_webui.utils.brain import organize_file

    file = await Files.get_file_by_id(id)
    if not file:
        raise HTTPException(status_code=404, detail='Ficheiro não encontrado.')
    _require_brain_access(file, user)

    result = await organize_file(request, id, user)
    if not result:
        raise HTTPException(
            status_code=503,
            detail='Não foi possível reorganizar agora (modelo ocupado). Tenta mais tarde.',
        )
    return result


@router.post('/brain/cleanup-duplicates', response_model=dict)
async def cleanup_duplicates(
    request: Request, user=Depends(get_verified_user), db: AsyncSession = Depends(get_async_session)
):
    """Gestor: remove cópias byte-a-byte idênticas, mantendo uma por grupo.

    Usa a mesma eliminação do DELETE /files/{id} (limpa knowledge, embeddings,
    storage e eventos). Sem admin, só opera sobre ficheiros do próprio.
    """
    # Passa as páginas (memória limitada) e guarda só metadados ligeiros.
    # Chave: hash dos BYTES (meta.file_hash) — apanha imagens/HEIC sem hash
    # de texto; fallback para o hash do texto extraído; depois o id.
    groups: dict[str, list] = {}
    skip = 0
    while True:
        items = await Files.get_duplicate_candidates(skip=skip, limit=100, db=db)
        if not items:
            break
        for item in items:
            if item['meta_file_hash']:
                key = f"bytes:{item['meta_file_hash']}"
            elif item['hash']:
                key = f"text:{item['hash']}"
            else:
                key = f"id:{item['id']}"
            groups.setdefault(key, []).append(
                {'id': item['id'], 'user_id': item['user_id'], 'filename': item['filename']}
            )
        if len(items) < 100:
            break
        skip += len(items)

    deleted = 0
    removed_names: list[str] = []
    for key, copies in groups.items():
        if len(copies) < 2:
            continue
        if user.role != 'admin' and any(c['user_id'] != user.id for c in copies):
            continue  # nunca mexe em ficheiros de outros utilizadores

        # Ligações à knowledge de CADA cópia — guardam-se antes de apagar
        # para que nenhuma colecção perca o ficheiro.
        links: dict[str, list] = {}
        for copy in copies:
            links[copy['id']] = await Knowledges.get_knowledges_by_file_id(copy['id'], db=db) or []

        # Manter: preferencialmente um com ligação a knowledge; senão o primeiro.
        keep = copies[0]
        for copy in copies:
            if links[copy['id']]:
                keep = copy
                break
        keep_knowledge_ids = {k.id for k in links[keep['id']]}

        for copy in copies:
            if copy['id'] == keep['id']:
                continue
            # Preserva as knowledge da cópia que vai ser apagada: re-liga-as
            # à que fica (o DELETE limpa as associações do ficheiro antigo).
            for knowledge in links[copy['id']]:
                if knowledge.id in keep_knowledge_ids:
                    continue
                try:
                    await Knowledges.add_file_to_knowledge_by_id(
                        knowledge_id=knowledge.id,
                        file_id=keep['id'],
                        user_id=copy['user_id'],
                        directory_id=None,
                        db=db,
                    )
                    keep_knowledge_ids.add(knowledge.id)
                except Exception:
                    log.warning(
                        'cleanup-duplicates: could not move knowledge %s to %s',
                        knowledge.id,
                        keep['id'],
                        exc_info=True,
                    )
            try:
                result = await delete_file_by_id(request, copy['id'], user, db=db)
                if isinstance(result, dict) and result.get('message'):
                    deleted += 1
                    removed_names.append(copy['filename'])
            except HTTPException:
                raise
            except Exception:
                log.warning('cleanup-duplicates: failed for %s', copy['id'], exc_info=True)

    log.info('brain: cleanup-duplicates removed %d copies (%d groups)', deleted, len(groups))
    return {
        'deleted': deleted,
        'groups': sum(1 for copies in groups.values() if len(copies) > 1),
        'files': removed_names[:50],
    }


@router.get('/brain/chat', response_model=dict)
async def get_brain_chat_history(user=Depends(get_verified_user)):
    """Histórico do chat com o cérebro — guardado no servidor, por utilizador."""
    from open_webui.utils.brain import load_chat_history

    return {'items': load_chat_history(user.id)}


@router.put('/brain/chat', response_model=dict)
async def put_brain_chat_history(request: Request, user=Depends(get_verified_user)):
    """Substitui o histórico do chat (mais recente primeiro; validado)."""
    from open_webui.utils.brain import save_chat_history

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail='invalid JSON body')

    items = payload.get('items') if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail='items must be a list')

    return {'status': True, 'count': save_chat_history(user.id, items)}


@router.delete('/brain/chat', response_model=dict)
async def delete_brain_chat_history(user=Depends(get_verified_user)):
    """Apaga o histórico do chat deste utilizador."""
    from open_webui.utils.brain import clear_chat_history

    clear_chat_history(user.id)
    return {'status': True}


@router.get('/search', response_model=list[FileModelResponse])
async def search_files(
    filename: str = Query(
        ...,
        description="Filename pattern to search for. Supports wildcards such as '*.txt'",
    ),
    content: bool = Query(True),
    skip: int = Query(0, ge=0, description='Number of files to skip'),
    limit: int = Query(100, ge=1, le=1000, description='Maximum number of files to return'),
    user=Depends(get_verified_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Search for files by filename with support for wildcard patterns.
    Uses SQL-based filtering with pagination for better performance.
    """
    # Determine user_id: null for admin with bypass (search all), user.id otherwise
    user_id = None if (user.role == 'admin' and BYPASS_ADMIN_ACCESS_CONTROL) else user.id

    # Use optimized database query with pagination
    files = await Files.search_files(
        user_id=user_id,
        filename=filename,
        skip=skip,
        limit=limit,
        db=db,
    )

    if not files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='No files found matching the pattern.',
        )

    if not content:
        for file in files:
            if file.data and 'content' in file.data:
                del file.data['content']

    return files


############################
# Count Files
############################


@router.get('/count', response_model=int)
async def count_files(
    user=Depends(get_verified_user),
    db: AsyncSession = Depends(get_async_session),
):
    user_id = None if (user.role == 'admin' and BYPASS_ADMIN_ACCESS_CONTROL) else user.id
    return await Files.count_files_by_user_id(user_id=user_id, db=db)


############################
# Delete All Files
############################


@router.delete('/all')
async def delete_all_files(
    request: Request, user=Depends(get_admin_user), db: AsyncSession = Depends(get_async_session)
):
    result = await Files.delete_all_files(db=db)
    if result:
        try:
            await asyncio.to_thread(Storage.delete_all_files)
            await ASYNC_VECTOR_DB_CLIENT.reset()
        except Exception as e:
            log.exception(e)
            log.error('Error deleting files')
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT('Error deleting files'),
            )
        await publish_event(request, EVENTS.FILE_DELETED_ALL, actor=user, subject_type='file')
        return {'message': 'All files deleted successfully'}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT('Error deleting files'),
        )


############################
# Get File By Id
############################


@router.get('/{id}', response_model=Optional[FileModel])
async def get_file_by_id(id: str, user=Depends(get_verified_user), db: AsyncSession = Depends(get_async_session)):
    file = await Files.get_file_by_id(id, db=db)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if file.user_id == user.id or user.role == 'admin' or await has_access_to_file(id, 'read', user, db=db):
        return file
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


@router.get('/{id}/process/status')
async def get_file_process_status(
    id: str,
    stream: bool = Query(False),
    user=Depends(get_verified_user),
):
    # NOTE: We intentionally do NOT use Depends(get_async_session) here.
    # Database operations manage their own short-lived sessions internally.
    # Holding a session here would keep a connection for the entire stream
    # (up to two hours) and exhaust the connection pool under concurrent load.
    file = await Files.get_file_by_id(id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if file.user_id == user.id or user.role == 'admin' or await has_access_to_file(id, 'read', user):
        if stream:
            MAX_FILE_PROCESSING_DURATION = 3600 * 2

            async def event_stream(file_id):
                for _ in range(MAX_FILE_PROCESSING_DURATION):
                    file_item = await Files.get_file_by_id(file_id)
                    if file_item:
                        data = file_item.model_dump().get('data', {})
                        status = data.get('status')

                        if status:
                            event = {'status': status}
                            if status == 'failed':
                                event['error'] = data.get('error')

                            yield f'data: {JSONCodec.dumps(event)}\n\n'
                            if status in ('completed', 'failed'):
                                break
                        else:
                            # Legacy
                            break
                    else:
                        yield f'data: {JSONCodec.dumps({"status": "not_found"})}\n\n'
                        break

                    await asyncio.sleep(1)

            return StreamingResponse(
                event_stream(file.id),
                media_type='text/event-stream',
            )
        else:
            return {'status': file.data.get('status', 'pending')}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# Get File Data Content By Id
############################


@router.get('/{id}/data/content')
async def get_file_data_content_by_id(
    id: str, user=Depends(get_verified_user), db: AsyncSession = Depends(get_async_session)
):
    file = await Files.get_file_by_id(id, db=db)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if file.user_id == user.id or user.role == 'admin' or await has_access_to_file(id, 'read', user, db=db):
        return {'content': file.data.get('content', '')}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# Update File Data Content By Id
############################


class ContentForm(BaseModel):
    content: str


@router.post('/{id}/data/content/update')
async def update_file_data_content_by_id(
    request: Request,
    id: str,
    form_data: ContentForm,
    user=Depends(get_verified_user),
    db: AsyncSession = Depends(get_async_session),
):
    file = await Files.get_file_by_id(id, db=db)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if file.user_id == user.id or user.role == 'admin' or await has_access_to_file(id, 'write', user, db=db):
        max_size = await Config.get('rag.file.max_size')
        if max_size and len(form_data.content.encode('utf-8')) > int(max_size) * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=ERROR_MESSAGES.FILE_TOO_LARGE(size=f'{max_size} MB'),
            )
        try:
            await process_file(
                request,
                ProcessFileForm(file_id=id, content=form_data.content),
                user=user,
                db=db,
            )
            file = await Files.get_file_by_id(id=id, db=db)
        except Exception as e:
            log.exception(e)
            log.error(f'Error processing file: {file.id}')

        # Propagate content change to all knowledge collections referencing
        # this file.  Without this the old embeddings remain in the knowledge
        # collection and RAG returns both stale and current data (#20558).
        knowledges = await Knowledges.get_knowledges_by_file_id(id, db=db)
        for knowledge in knowledges:
            try:
                old_vectors = await ASYNC_VECTOR_DB_CLIENT.query(collection_name=knowledge.id, filter={'file_id': id})
                old_vector_ids = old_vectors.ids[0] if old_vectors and old_vectors.ids else []

                # Re-add from the now-updated file-{file_id} collection before
                # removing old vectors, so a failed reindex keeps the KB usable.
                await process_file(
                    request,
                    ProcessFileForm(file_id=id, collection_name=knowledge.id),
                    user=user,
                    db=db,
                )
                if old_vector_ids:
                    await ASYNC_VECTOR_DB_CLIENT.delete(collection_name=knowledge.id, ids=old_vector_ids)
            except Exception as e:
                log.warning(f'Failed to update knowledge {knowledge.id} after content change for file {id}: {e}')

        await publish_event(
            request,
            EVENTS.FILE_CONTENT_UPDATED,
            actor=user,
            subject_id=id,
            data={'content_preview': form_data.content[:300]},
        )
        return {'content': file.data.get('content', '')}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# Get File Content By Id
############################


@router.get('/{id}/content')
async def get_file_content_by_id(
    id: str,
    user=Depends(get_verified_user),
    attachment: bool = Query(False),
    db: AsyncSession = Depends(get_async_session),
):
    file = await Files.get_file_by_id(id, db=db)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if file.user_id == user.id or user.role == 'admin' or await has_access_to_file(id, 'read', user, db=db):
        try:
            file_path = await asyncio.to_thread(Storage.get_file, file.path)
            file_path = Path(file_path)

            # Check if the file already exists in the cache
            if file_path.is_file():
                # Handle Unicode filenames
                filename = file.meta.get('name', file.filename)
                encoded_filename = quote(filename)  # RFC5987 encoding

                content_type = file.meta.get('content_type')
                filename = file.meta.get('name', file.filename)
                encoded_filename = quote(filename)
                headers = {}

                if attachment:
                    headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"
                else:
                    if content_type == 'application/pdf' or filename.lower().endswith('.pdf'):
                        headers['Content-Disposition'] = f"inline; filename*=UTF-8''{encoded_filename}"
                        content_type = 'application/pdf'
                    elif content_type != 'text/plain':
                        headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"

                return FileResponse(file_path, headers=headers, media_type=content_type)

            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ERROR_MESSAGES.NOT_FOUND,
                )
        except HTTPException as e:
            raise e
        except Exception as e:
            log.exception(e)
            log.error('Error getting file content')
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT('Error getting file content'),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


@router.get('/{id}/content/html')
async def get_html_file_content_by_id(
    id: str, user=Depends(get_verified_user), db: AsyncSession = Depends(get_async_session)
):
    file = await Files.get_file_by_id(id, db=db)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    file_user = await Users.get_user_by_id(file.user_id, db=db)
    if not file_user or file_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if file.user_id == user.id or user.role == 'admin' or await has_access_to_file(id, 'read', user, db=db):
        try:
            file_path = await asyncio.to_thread(Storage.get_file, file.path)
            file_path = Path(file_path)

            # Check if the file already exists in the cache
            if file_path.is_file():
                log.info('file_path: %s', file_path)
                return FileResponse(file_path)
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ERROR_MESSAGES.NOT_FOUND,
                )
        except HTTPException as e:
            raise e
        except Exception as e:
            log.exception(e)
            log.error('Error getting file content')
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT('Error getting file content'),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


@router.get('/{id}/content/{file_name}')
async def get_file_content_by_id(
    id: str, user=Depends(get_verified_user), db: AsyncSession = Depends(get_async_session)
):
    file = await Files.get_file_by_id(id, db=db)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if file.user_id == user.id or user.role == 'admin' or await has_access_to_file(id, 'read', user, db=db):
        file_path = file.path

        # Handle Unicode filenames
        filename = file.meta.get('name', file.filename)
        encoded_filename = quote(filename)  # RFC5987 encoding
        headers = {'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}"}

        if file_path:
            file_path = await asyncio.to_thread(Storage.get_file, file_path)
            file_path = Path(file_path)

            # Check if the file already exists in the cache
            if file_path.is_file():
                return FileResponse(file_path, headers=headers)
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ERROR_MESSAGES.NOT_FOUND,
                )
        else:
            # File path doesn’t exist, return the content as .txt if possible
            file_content = file.data.get('content', '')
            file_name = file.filename

            # Create a generator that encodes the file content
            def generator():
                yield file_content.encode('utf-8')

            return StreamingResponse(
                generator(),
                media_type='text/plain',
                headers=headers,
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# Rename File By Id
############################


class FileRenameForm(BaseModel):
    filename: str


@router.post('/{id}/rename')
async def rename_file_by_id(
    request: Request,
    id: str,
    form_data: FileRenameForm,
    user=Depends(get_verified_user),
    db: AsyncSession = Depends(get_async_session),
):
    file = await Files.get_file_by_id(id, db=db)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if file.user_id == user.id or user.role == 'admin' or await has_access_to_file(id, 'write', user, db=db):
        result = await Files.update_file_name_by_id(id, form_data.filename, db=db)
        if result:
            await publish_event(
                request,
                EVENTS.FILE_RENAMED,
                actor=user,
                subject_id=id,
                data={'filename': form_data.filename},
            )
            return result
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT('Error renaming file'),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# Delete File By Id
############################


@router.delete('/{id}')
async def delete_file_by_id(
    request: Request, id: str, user=Depends(get_verified_user), db: AsyncSession = Depends(get_async_session)
):
    file = await Files.get_file_by_id(id, db=db)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if file.user_id == user.id or user.role == 'admin' or await has_access_to_file(id, 'write', user, db=db):
        # Clean up KB associations and embeddings before deleting
        knowledges = await Knowledges.get_knowledges_by_file_id(id, db=db)
        for knowledge in knowledges:
            # Remove KB-file relationship
            await Knowledges.remove_file_from_knowledge_by_id(knowledge.id, id, db=db)
            # Clean KB embeddings (same logic as /knowledge/{id}/file/remove)
            try:
                await ASYNC_VECTOR_DB_CLIENT.delete(collection_name=knowledge.id, filter={'file_id': id})
                if file.hash:
                    await ASYNC_VECTOR_DB_CLIENT.delete(collection_name=knowledge.id, filter={'hash': file.hash})
            except Exception as e:
                log.debug('KB embedding cleanup for %s: %s', knowledge.id, e)

        result = await Files.delete_file_by_id(id, db=db)
        if result:
            try:
                await asyncio.to_thread(Storage.delete_file, file.path)
                await ASYNC_VECTOR_DB_CLIENT.delete(collection_name=f'file-{id}')
            except Exception as e:
                log.exception(e)
                log.error('Error deleting files')
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT('Error deleting files'),
                )
            await publish_event(
                request,
                EVENTS.FILE_DELETED,
                actor=user,
                subject_id=id,
                data={'filename': file.filename},
            )
            return {'message': 'File deleted successfully'}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT('Error deleting file'),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )
