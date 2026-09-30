import json
import logging
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

log = logging.getLogger(__name__)

# Nomes amigáveis das formas para o inventário (pt-PT).
SHAPE_LABELS = {
    'rectangle': 'retângulo',
    'ellipse': 'elipse',
    'diamond': 'losango',
    'arrow': 'seta',
    'line': 'linha',
    'frame': 'moldura',
    'freedraw': 'desenho à mão',
    'image': 'imagem',
    'text': 'texto',
}


class ExcalidrawLoader(BaseLoader):
    """Lê ficheiros ``.excalidraw`` (JSON) e extrai o que está desenhado.

    Em vez de indexar o JSON bruto (inútil para pesquisa/perguntas), guardamos:
      • um inventário das formas (n tipos, quantas);
      • todos os textos das caixas de texto — é o que torna o diagrama
        pesquisável no Knowledge e consultável pelo Modo Cérebro.

    Se o ficheiro não for JSON válido, devolve-o como texto puro (nada se
    perde). Diagramas sem texto continuam a ter conteúdo (o inventário).
    """

    def __init__(self, file_path):
        self.file_path = str(Path(file_path).expanduser())

    def lazy_load(self):
        name = Path(self.file_path).name
        try:
            raw = Path(self.file_path).read_text(encoding='utf-8', errors='replace')
        except OSError as exc:
            log.warning('Excalidraw: could not read %s: %s', self.file_path, exc)
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Não é JSON válido — guardar como texto para não perder nada.
            yield Document(
                page_content=raw.strip(),
                metadata={'source': self.file_path, 'file_name': name},
            )
            return

        elements = []
        if isinstance(data, dict) and (
            data.get('type') in ('excalidraw', 'excalidrawlib') or isinstance(data.get('elements'), list)
        ):
            elements = data.get('elements') or []
        elif isinstance(data, list):
            elements = data

        texts: list[str] = []
        counts: dict[str, int] = {}
        for element in elements:
            if not isinstance(element, dict) or element.get('isDeleted'):
                continue
            etype = str(element.get('type') or 'unknown')
            counts[etype] = counts.get(etype, 0) + 1
            if etype == 'text':
                label = str(element.get('text') or '').strip()
                if label:
                    texts.append(label)

        inventory = ', '.join(
            f'{total}× {SHAPE_LABELS.get(etype, etype)}'
            for etype, total in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        )
        parts = [f'[Diagrama Excalidraw: {inventory}]' if inventory else '[Diagrama Excalidraw]']
        if texts:
            parts.append('Texto do diagrama:\n' + '\n'.join(texts))
        content = '\n\n'.join(parts).strip()

        yield Document(
            page_content=content,
            metadata={
                'source': self.file_path,
                'file_name': name,
                'excalidraw': True,
                'elements': len(elements),
                'has_text': bool(texts),
            },
        )
