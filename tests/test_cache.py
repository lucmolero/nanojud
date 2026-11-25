from uuid import uuid4

import pytest

from nanojud.cache import JsonFileCache


def test_json_file_cache_roundtrip():
    cache = JsonFileCache(directory=".tmp/test-cache", ttl_seconds=60)

    cache.set("extrato", "processo-cache", {"status": "ok"})

    assert cache.get("extrato", "processo-cache") == {"status": "ok"}


def test_json_file_cache_miss():
    cache = JsonFileCache(directory=".tmp/test-cache", ttl_seconds=60)

    assert cache.get("extrato", "inexistente") is None


def test_namespace_cache_nao_escapa_do_diretorio_raiz(tmp_path):
    cache = JsonFileCache(directory=tmp_path / "cache", ttl_seconds=60)
    path = cache._path("..", "processo")

    assert path.parent.resolve().is_relative_to(cache.directory.resolve())


@pytest.mark.parametrize("ttl", [-1, True, 1.5, "60"])
def test_json_file_cache_rejeita_ttl_invalido(ttl, tmp_path):
    with pytest.raises(ValueError, match="cache_ttl_seconds"):
        JsonFileCache(directory=tmp_path, ttl_seconds=ttl)


def test_json_file_cache_expirado():
    cache = JsonFileCache(directory=f".tmp/test-cache-expirado-{uuid4()}", ttl_seconds=1)
    path = cache.set("extrato", "processo-expirado", {"status": "ok"})
    path.write_text('{"created_at": 0, "value": {"status": "ok"}}', encoding="utf-8")

    assert cache.get("extrato", "processo-expirado") is None


def test_json_file_cache_ignora_json_corrompido():
    cache = JsonFileCache(directory=f".tmp/test-cache-corrompido-{uuid4()}", ttl_seconds=60)
    path = cache.set("extrato", "processo-corrompido", {"status": "ok"})
    path.write_text("{json inválido", encoding="utf-8")

    assert cache.get("extrato", "processo-corrompido") is None


@pytest.mark.parametrize(
    "conteudo",
    [
        "[]",
        "null",
        '{"created_at":"inválido","value":{"status":"ok"}}',
        '{"created_at":NaN,"value":{"status":"ok"}}',
        '{"created_at":Infinity,"value":{"status":"ok"}}',
    ],
)
def test_json_file_cache_ignora_metadados_invalidos(conteudo, tmp_path):
    cache = JsonFileCache(directory=tmp_path, ttl_seconds=60)
    path = cache.set("extrato", "processo-metadados", {"status": "ok"})
    path.write_text(conteudo, encoding="utf-8")

    assert cache.get("extrato", "processo-metadados") is None


def test_falha_ao_gravar_cache_preserva_a_entrada_anterior(monkeypatch, tmp_path):
    import tempfile

    import nanojud.cache as cache_module

    cache = JsonFileCache(directory=tmp_path, ttl_seconds=60)
    path = cache.set("extrato", "processo-atomico", {"status": "anterior"})
    named_temp_original = tempfile.NamedTemporaryFile

    class GravaParcialmente:
        def __init__(self, **kwargs):
            self._arquivo = named_temp_original(**kwargs)
            self.name = self._arquivo.name

        def __enter__(self):
            self._arquivo.__enter__()
            return self

        def __exit__(self, *args):
            return self._arquivo.__exit__(*args)

        def write(self, conteudo):
            self._arquivo.write(conteudo[:8])
            raise OSError("falha simulada durante a gravação")

    monkeypatch.setattr(cache_module.tempfile, "NamedTemporaryFile", GravaParcialmente)
    with pytest.raises(OSError, match="falha simulada"):
        cache.set("extrato", "processo-atomico", {"status": "novo"})

    assert cache.get("extrato", "processo-atomico") == {"status": "anterior"}
    assert list(path.parent.glob(f".{path.name}.*.tmp")) == []
