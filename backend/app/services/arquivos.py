"""Storage de arquivos (documentos e dossiês).

Dois backends atrás da mesma interface:
  - local: disco (desenvolvimento e testes);
  - blob:  Azure Blob Storage (produção). No Azure Functions o disco é efêmero e há várias instâncias,
           então nada que o usuário enviou ou que o sistema gerou pode ficar no disco.
"""

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Documento


class Backend(Protocol):
    def salvar(self, relativo: str, conteudo: bytes) -> None: ...
    def ler(self, relativo: str) -> bytes: ...  # levanta FileNotFoundError se não existir
    def apagar(self, relativo: str) -> None: ...  # não falha se o arquivo não existir


class BackendDisco:
    def __init__(self, raiz: Path):
        self.raiz = raiz

    def salvar(self, relativo: str, conteudo: bytes) -> None:
        destino = self.raiz / relativo
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)

    def ler(self, relativo: str) -> bytes:
        return (self.raiz / relativo).read_bytes()

    def apagar(self, relativo: str) -> None:
        try:
            (self.raiz / relativo).unlink(missing_ok=True)
        except OSError:
            pass


class BackendBlob:
    def __init__(self, container):
        self.container = container

    def salvar(self, relativo: str, conteudo: bytes) -> None:
        self.container.upload_blob(name=relativo, data=conteudo, overwrite=True)

    def ler(self, relativo: str) -> bytes:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self.container.download_blob(relativo).readall()
        except ResourceNotFoundError:
            raise FileNotFoundError(relativo)

    def apagar(self, relativo: str) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            self.container.delete_blob(relativo)
        except ResourceNotFoundError:
            pass


def _criar_blob() -> BackendBlob:
    from azure.core.exceptions import ResourceExistsError
    from azure.storage.blob import BlobServiceClient

    if settings.blob_connection_string:  # Azurite / desenvolvimento
        servico = BlobServiceClient.from_connection_string(settings.blob_connection_string)
        container = servico.get_container_client(settings.blob_container)
        try:
            container.create_container()
        except ResourceExistsError:
            pass
        return BackendBlob(container)

    if not settings.blob_account_url:
        raise RuntimeError("STORAGE_BACKEND=blob exige BLOB_ACCOUNT_URL (ou BLOB_CONNECTION_STRING no dev).")
    from azure.identity import DefaultAzureCredential

    # Identidade gerenciada da Function; o contêiner é criado pelo infra/azure-functions.sh
    servico = BlobServiceClient(settings.blob_account_url, credential=DefaultAzureCredential())
    return BackendBlob(servico.get_container_client(settings.blob_container))


@lru_cache(maxsize=1)
def _padrao() -> Backend:
    if settings.storage_backend == "blob":
        return _criar_blob()
    return BackendDisco(settings.storage_dir)


_substituto: Backend | None = None


def usar_backend(backend: Backend | None) -> None:
    """Troca o backend (testes). `None` volta ao definido pela configuração."""
    global _substituto
    _substituto = backend


def _backend() -> Backend:
    return _substituto or _padrao()


def salvar(relativo: str, conteudo: bytes) -> str:
    _backend().salvar(relativo, conteudo)
    return relativo


def ler(relativo: str) -> bytes:
    return _backend().ler(relativo)


def sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def apagar_arquivos(caminhos: list[str]) -> None:
    for relativo in caminhos:
        _backend().apagar(relativo)


def caminhos_documentos(db: Session, *, fornecedor_id: int | None = None, fazenda_id: int | None = None) -> list[str]:
    """Caminhos dos arquivos que serão removidos em cascata junto com o dono."""
    consulta = select(Documento.caminho_storage)
    if fornecedor_id is not None:
        # documentos do fornecedor e das fazendas dele
        from app.models import Fazenda

        ids = select(Fazenda.id).where(Fazenda.fornecedor_id == fornecedor_id)
        consulta = consulta.where(
            (Documento.fornecedor_id == fornecedor_id) | (Documento.fazenda_id.in_(ids))
        )
    else:
        consulta = consulta.where(Documento.fazenda_id == fazenda_id)
    return list(db.scalars(consulta))
