"""Backend de Blob testado com um contêiner falso: nada pode ir para o disco (Functions tem disco efêmero)."""

from pathlib import Path

import pytest
from azure.core.exceptions import ResourceNotFoundError

from app.config import settings
from app.services import arquivos
from tests.conftest import quadrado

PDF = b"%PDF-1.4\n%%EOF"


class _Baixado:
    def __init__(self, dados: bytes):
        self._dados = dados

    def readall(self) -> bytes:
        return self._dados


class ContainerFalso:
    """Imita só o que BackendBlob usa de azure.storage.blob.ContainerClient."""

    def __init__(self):
        self.blobs: dict[str, bytes] = {}

    def upload_blob(self, name, data, overwrite=False):
        if not overwrite and name in self.blobs:
            raise AssertionError("sobrescrita sem overwrite=True")
        self.blobs[name] = bytes(data)

    def download_blob(self, name):
        if name not in self.blobs:
            raise ResourceNotFoundError("não existe")
        return _Baixado(self.blobs[name])

    def delete_blob(self, name):
        if name not in self.blobs:
            raise ResourceNotFoundError("não existe")
        del self.blobs[name]


@pytest.fixture
def blob():
    container = ContainerFalso()
    arquivos.usar_backend(arquivos.BackendBlob(container))
    yield container
    arquivos.usar_backend(None)


def test_salvar_ler_apagar(blob):
    assert arquivos.salvar("a/b.pdf", PDF) == "a/b.pdf"
    assert arquivos.ler("a/b.pdf") == PDF
    arquivos.salvar("a/b.pdf", b"novo")  # sobrescreve
    assert arquivos.ler("a/b.pdf") == b"novo"
    arquivos.apagar_arquivos(["a/b.pdf", "nao-existe.pdf"])  # ausente não falha
    with pytest.raises(FileNotFoundError):
        arquivos.ler("a/b.pdf")


def test_blob_sem_configuracao_falha_com_mensagem_clara(monkeypatch):
    monkeypatch.setattr(settings, "blob_account_url", None)
    monkeypatch.setattr(settings, "blob_connection_string", None)
    with pytest.raises(RuntimeError, match="BLOB_ACCOUNT_URL"):
        arquivos._criar_blob()


def test_documentos_vao_para_o_blob_e_nao_para_o_disco(client, auth, fornecedor, blob):
    r = client.post(
        f"/fornecedores/{fornecedor['id']}/documentos",
        headers=auth,
        files={"arquivo": ("relatório CAR.pdf", PDF)},
        data={"tipo": "car"},
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert len(blob.blobs) == 1 and next(iter(blob.blobs.values())) == PDF
    assert not any(Path(settings.storage_dir).rglob("*"))  # nada no disco

    baixado = client.get(f"/documentos/{doc['id']}/arquivo", headers=auth)
    assert baixado.status_code == 200 and baixado.content == PDF
    assert baixado.headers["content-disposition"].startswith("attachment; filename*=UTF-8''")
    assert "relat%C3%B3rio%20CAR.pdf" in baixado.headers["content-disposition"]  # acento codificado

    assert client.delete(f"/documentos/{doc['id']}", headers=auth).status_code == 204
    assert blob.blobs == {}


def test_documento_ausente_no_blob_devolve_410(client, auth, fornecedor, blob):
    doc = client.post(
        f"/fornecedores/{fornecedor['id']}/documentos", headers=auth,
        files={"arquivo": ("car.pdf", PDF)}, data={"tipo": "car"},
    ).json()
    blob.blobs.clear()
    assert client.get(f"/documentos/{doc['id']}/arquivo", headers=auth).status_code == 410


def test_excluir_fornecedor_remove_blobs_dele_e_das_fazendas(client, auth, fornecedor, camada, blob):
    f = client.post("/fazendas", headers=auth, json={"fornecedor_id": fornecedor["id"], "nome": "Faz", "geometry": quadrado(-49.5, -21.5, 0.01)}).json()
    for url in (f"/fornecedores/{fornecedor['id']}/documentos", f"/fazendas/{f['id']}/documentos"):
        assert client.post(url, headers=auth, files={"arquivo": ("d.pdf", PDF)}, data={"tipo": "outro"}).status_code == 201
    assert len(blob.blobs) == 2
    assert client.delete(f"/fazendas/{f['id']}", headers=auth).status_code == 204
    assert len(blob.blobs) == 1
    assert client.delete(f"/fornecedores/{fornecedor['id']}", headers=auth).status_code == 204
    assert blob.blobs == {}


def test_dossie_gerado_e_baixado_pelo_blob(client, auth, fornecedor, camada, blob):
    f = client.post("/fazendas", headers=auth, json={"fornecedor_id": fornecedor["id"], "nome": "Faz", "geometry": quadrado(-49.5, -21.5, 0.01)}).json()
    e = client.post("/embarques", headers=auth, json={"identificacao": "EMB-1", "data_embarque": "2027-01-10", "destino": "Rotterdam"}).json()
    client.put(f"/embarques/{e['id']}/parcelas", headers=auth, json={"parcelas": [{"fazenda_id": f["id"], "quantidade_kg": 500}]})
    d = client.post(f"/embarques/{e['id']}/fechar", headers=auth).json()["dossie_id"]
    assert sorted(k.rsplit("/", 1)[1] for k in blob.blobs) == ["dossie.geojson", "dossie.pdf"]
    assert not any(Path(settings.storage_dir).rglob("*"))
    assert client.get(f"/dossies/{d}/pdf", headers=auth).content.startswith(b"%PDF")
    assert client.get(f"/dossies/{d}/geojson", headers=auth).json()["type"] == "FeatureCollection"
