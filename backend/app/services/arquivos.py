"""Storage de arquivos (documentos e dossiês). Em desenvolvimento: disco local."""

import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Documento


def raiz() -> Path:
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    return settings.storage_dir


def salvar(relativo: str, conteudo: bytes) -> str:
    destino = raiz() / relativo
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(conteudo)
    return relativo


def ler(relativo: str) -> bytes:
    return (raiz() / relativo).read_bytes()


def existe(relativo: str) -> bool:
    return (raiz() / relativo).is_file()


def sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def apagar_arquivos(caminhos: list[str]) -> None:
    for relativo in caminhos:
        try:
            (raiz() / relativo).unlink(missing_ok=True)
        except OSError:
            pass


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
