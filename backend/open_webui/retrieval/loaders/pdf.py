import datetime as dt
import io
import logging
import os
import threading
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

log = logging.getLogger(__name__)

# OCR local de páginas digitalizadas (renderiza com PyMuPDF → RapidOCR).
# Cobertura: PDFs sem camada de texto E sem imagens embutidas detectáveis
# (ex.: imagens dentro de Form XObjects). Env: PDF_RENDER_OCR_MAX_PAGES.
RENDER_OCR_MAX_PAGES = int(os.getenv('PDF_RENDER_OCR_MAX_PAGES', '50'))
_OCR_ZOOM = 1.5  # ~108 dpi — equilíbrio entre legibilidade e custo
_ocr_engine = None
_ocr_lock = threading.Lock()

_PIXMAP_MODES = {1: 'L', 2: 'LA', 3: 'RGB', 4: 'RGBA'}


def _pixels_from_pixmap(pixmap):
    import numpy as np
    from PIL import Image

    mode = _PIXMAP_MODES.get(pixmap.n, 'RGB')
    image = Image.frombytes(mode, (pixmap.width, pixmap.height), pixmap.samples)
    if image.mode != 'RGB':
        image = image.convert('RGB')
    return np.array(image)


def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr import RapidOCR

        _ocr_engine = RapidOCR()
    return _ocr_engine


def ocr_pdf_text(file_path, pages=None, max_pages=RENDER_OCR_MAX_PAGES) -> str:
    """OCR local de páginas de um PDF digitalizado (PyMuPDF + RapidOCR).

    ``pages`` (lista de índices) processa só essas páginas; caso contrário as
    primeiras ``max_pages``. Devolve '' se não houver OCR disponível ou texto —
    nunca levanta exceção (é um caminho de recurso).
    """
    if not file_path:
        return ''
    try:
        import pymupdf
    except Exception:
        log.warning('PDF OCR local: pymupdf indisponível', exc_info=True)
        return ''

    try:
        with pymupdf.open(str(file_path)) as document:
            if pages is None:
                indexes = range(min(max_pages, document.page_count))
            else:
                indexes = [i for i in pages if 0 <= i < document.page_count]
            texts = []
            # Serializa: o motor OCR é CPU-bound e não é thread-safe.
            with _ocr_lock:
                engine = _get_ocr_engine()
                for index in indexes:
                    page = document.load_page(index)
                    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(_OCR_ZOOM, _OCR_ZOOM))
                    result = engine(_pixels_from_pixmap(pixmap))
                    if result and getattr(result, 'txts', None):
                        texts.append('\n'.join(t for t in result.txts if t))
            return '\n\n'.join(t for t in texts if t).strip()
    except Exception:
        log.warning('PDF OCR local falhou para %s', file_path, exc_info=True)
        return ''


class PDFLoader(BaseLoader):
    def __init__(self, file_path, *, extract_images=False, mode='page'):
        if mode not in ('single', 'page'):
            raise ValueError("PDF mode must be 'single' or 'page'")
        self.file_path = str(Path(file_path).expanduser())
        self.extract_images = extract_images
        self.mode = mode
        self.ocr = None
        self._rendered_ocr = 0

    def _page_text(self, page, index: int) -> str:
        """Texto de uma página: pypdf → imagens embutidas → OCR local."""
        text = page.extract_text()
        if self.extract_images:
            image_text = self._extract_images(page)
            if image_text:
                text = self._merge_image_text(text, image_text)
        text = (text or '').strip()
        if not text and self._rendered_ocr < RENDER_OCR_MAX_PAGES:
            # Página digitalizada sem NENHUM texto: renderiza e faz OCR LOCAL
            # (offline, sem modelo). Independente de PDF_EXTRACT_IMAGES — um
            # PDF scan devolver sempre vazio é o que fazia uploads falharem.
            self._rendered_ocr += 1
            text = ocr_pdf_text(self.file_path, pages=[index])
        return text

    def lazy_load(self):
        from pypdf import PdfReader

        with open(self.file_path, 'rb') as file:
            reader = PdfReader(file)
            metadata = {'producer': 'PyPDF', 'creator': 'PyPDF', 'creationdate': ''}
            for key, value in (reader.metadata or {}).items():
                key = key.removeprefix('/').lower()
                value = value if type(value) in (str, int) else str(value)
                if key in ('creationdate', 'moddate') and isinstance(value, str):
                    try:
                        value = dt.datetime.strptime(value.replace("'", ''), 'D:%Y%m%d%H%M%S%z').isoformat()
                    except ValueError:
                        pass
                metadata[key] = (
                    value.strip()
                    if isinstance(value, str) and key not in ('creationdate', 'moddate', 'page_count', 'file_path')
                    else value
                )
            metadata.update(source=self.file_path, total_pages=len(reader.pages))
            labels = reader.page_labels if self.mode == 'page' else None
            texts = []
            for index, page in enumerate(reader.pages):
                text = self._page_text(page, index)
                if self.mode == 'page':
                    yield Document(page_content=text, metadata={**metadata, 'page': index, 'page_label': labels[index]})
                else:
                    texts.append(text)
            if self.mode == 'single':
                yield Document(page_content='\n\f'.join(texts), metadata=metadata)

    @staticmethod
    def _merge_image_text(text, image_text):
        # Insert before the final paragraphs/footer where possible, matching existing chunks.
        position, separator = len(text), '\n\n'
        for _ in range(2):
            for delimiter in ('\n\n\n', '\n\n'):
                found = text.rfind(delimiter, 0, position)
                if found >= 0:
                    position, separator = found, delimiter
                    break
            else:
                break
        return text[:position] + separator + image_text + text[position:]

    def _extract_images(self, page):
        import numpy as np
        from PIL import Image, UnidentifiedImageError

        if '/Resources' not in page or '/XObject' not in page['/Resources']:
            return ''
        texts = []
        xobjects = page['/Resources']['/XObject']
        for name in xobjects:
            try:
                stream = xobjects[name]
                if stream.get('/Subtype') != '/Image':
                    continue
                try:
                    # Encoded images, including CMYK JPEGs, can go straight to Pillow.
                    image = Image.open(io.BytesIO(stream.get_data()))
                except UnidentifiedImageError:
                    image = stream.decode_as_image()
                pixels = np.array(image.convert('RGB'))
            except Exception as e:
                log.warning('Skipping unreadable PDF image %s: %s', name, e)
                continue

            if self.ocr is None:
                from rapidocr import RapidOCR

                self.ocr = RapidOCR()
            result = self.ocr(pixels)
            if result and result.txts:
                texts.append('\n'.join(result.txts).strip())
        return '\n\n' + '\n'.join(filter(None, texts)) + '\n\n' if any(texts) else ''
