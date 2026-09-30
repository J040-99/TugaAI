import json


def _write(tmp_path, payload):
    path = tmp_path / 'desenho.excalidraw'
    path.write_text(
        payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False),
        encoding='utf-8',
    )
    return str(path)


def test_excalidraw_loader_extrai_texto_e_inventario(tmp_path):
    from open_webui.retrieval.loaders.excalidraw import ExcalidrawLoader

    payload = {
        'type': 'excalidraw',
        'elements': [
            {'type': 'rectangle', 'x': 0, 'y': 0, 'isDeleted': False},
            {'type': 'text', 'text': 'Base de dados', 'isDeleted': False},
            {'type': 'text', 'text': 'API REST', 'isDeleted': False},
            {'type': 'text', 'text': '   ', 'isDeleted': False},
            {'type': 'arrow', 'isDeleted': True},  # apagado → ignorado
            {'type': 'ellipse', 'isDeleted': False},
        ],
    }
    docs = list(ExcalidrawLoader(_write(tmp_path, payload)).lazy_load())

    assert len(docs) == 1
    content = docs[0].page_content
    assert 'Base de dados' in content
    assert 'API REST' in content
    assert 'retângulo' in content
    assert 'elipse' in content
    assert 'seta' not in content  # elemento apagado não conta
    assert content.startswith('[Diagrama Excalidraw')
    assert docs[0].metadata['has_text'] is True


def test_excalidraw_loader_diagrama_sem_texto_continua_com_inventario(tmp_path):
    from open_webui.retrieval.loaders.excalidraw import ExcalidrawLoader

    payload = {'type': 'excalidraw', 'elements': [{'type': 'rectangle'}]}
    docs = list(ExcalidrawLoader(_write(tmp_path, payload)).lazy_load())

    content = docs[0].page_content
    assert 'retângulo' in content
    assert len(content) > 10  # nunca vazio (process_file rejeita <40? não — mas fica útil)
    assert docs[0].metadata['has_text'] is False


def test_excalidraw_loader_json_invalido_devolve_texto_bruto(tmp_path):
    from open_webui.retrieval.loaders.excalidraw import ExcalidrawLoader

    raw = 'isto nao e json {corrompido'
    docs = list(ExcalidrawLoader(_write(tmp_path, raw)).lazy_load())

    assert docs[0].page_content == raw


def test_excalidraw_loader_ficheiro_em_falta_nao_levanta(tmp_path):
    from open_webui.retrieval.loaders.excalidraw import ExcalidrawLoader

    assert list(ExcalidrawLoader(str(tmp_path / 'nao-existe.excalidraw')).lazy_load()) == []
