import uuid
from datetime import date
from pathlib import PurePath
from urllib.parse import quote
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import usuario_atual
from app.config import settings
from app.database import get_db
from app.models import Documento, Usuario
from app.routers.fazendas import obter_fazenda
from app.routers.fornecedores import obter_fornecedor
from app.schemas import DocumentoOut, TipoDocumento
from app.services import arquivos

router = APIRouter(tags=["documentos"])

# Tipo real é decidido pelo conteúdo, não pelo que o cliente declara.
_ASSINATURAS = (
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
)


def _detectar(conteudo: bytes) -> tuple[str, str]:
    for assinatura, mime, extensao in _ASSINATURAS:
        if conteudo.startswith(assinatura):
            return mime, extensao
    raise HTTPException(400, detail="Formato não aceito. Envie PDF, PNG ou JPG.")


def _nome_seguro(nome: str | None) -> str:
    base = PurePath((nome or "documento").replace("\\", "/")).name
    return base[:255] or "documento"


async def _salvar_upload(
    db: Session,
    usuario: Usuario,
    arquivo: UploadFile,
    tipo: str,
    validade: date | None,
    *,
    fornecedor_id: int | None = None,
    fazenda_id: int | None = None,
) -> Documento:
    limite = settings.upload_max_mb * 1024 * 1024
    conteudo = await arquivo.read(limite + 1)
    if len(conteudo) > limite:
        raise HTTPException(413, detail=f"Arquivo maior que o limite de {settings.upload_max_mb} MB.")
    if not conteudo:
        raise HTTPException(400, detail="Arquivo vazio.")
    mime, extensao = _detectar(conteudo)

    relativo = f"documentos/{usuario.id}/{uuid.uuid4().hex}{extensao}"
    arquivos.salvar(relativo, conteudo)
    documento = Documento(
        usuario_id=usuario.id,
        fornecedor_id=fornecedor_id,
        fazenda_id=fazenda_id,
        tipo=tipo,
        nome_arquivo=_nome_seguro(arquivo.filename),
        caminho_storage=relativo,
        content_type=mime,
        tamanho_bytes=len(conteudo),
        sha256=arquivos.sha256(conteudo),
        validade=validade,
    )
    db.add(documento)
    try:
        db.commit()
    except Exception:
        db.rollback()
        arquivos.apagar_arquivos([relativo])
        raise
    return documento


Upload = Annotated[UploadFile, File(description="PDF, PNG ou JPG")]


@router.post("/fornecedores/{fornecedor_id}/documentos", response_model=DocumentoOut, status_code=201)
async def anexar_ao_fornecedor(
    fornecedor_id: int,
    arquivo: Upload,
    tipo: Annotated[TipoDocumento, Form()],
    validade: Annotated[date | None, Form()] = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    obter_fornecedor(db, usuario, fornecedor_id)
    return await _salvar_upload(db, usuario, arquivo, tipo, validade, fornecedor_id=fornecedor_id)


@router.post("/fazendas/{fazenda_id}/documentos", response_model=DocumentoOut, status_code=201)
async def anexar_a_fazenda(
    fazenda_id: int,
    arquivo: Upload,
    tipo: Annotated[TipoDocumento, Form()],
    validade: Annotated[date | None, Form()] = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    obter_fazenda(db, usuario, fazenda_id)
    return await _salvar_upload(db, usuario, arquivo, tipo, validade, fazenda_id=fazenda_id)


@router.get("/fornecedores/{fornecedor_id}/documentos", response_model=list[DocumentoOut])
def listar_do_fornecedor(fornecedor_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    obter_fornecedor(db, usuario, fornecedor_id)
    return db.scalars(
        select(Documento).where(Documento.fornecedor_id == fornecedor_id, Documento.usuario_id == usuario.id)
        .order_by(Documento.id)
    ).all()


@router.get("/fazendas/{fazenda_id}/documentos", response_model=list[DocumentoOut])
def listar_da_fazenda(fazenda_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    obter_fazenda(db, usuario, fazenda_id)
    return db.scalars(
        select(Documento).where(Documento.fazenda_id == fazenda_id, Documento.usuario_id == usuario.id)
        .order_by(Documento.id)
    ).all()


def _obter_documento(db: Session, usuario: Usuario, documento_id: int) -> Documento:
    documento = db.scalar(
        select(Documento).where(Documento.id == documento_id, Documento.usuario_id == usuario.id)
    )
    if documento is None:
        raise HTTPException(404, detail="Documento não encontrado.")
    return documento


@router.get("/documentos/{documento_id}/arquivo")
def baixar(documento_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    documento = _obter_documento(db, usuario, documento_id)
    try:
        conteudo = arquivos.ler(documento.caminho_storage)
    except FileNotFoundError:
        raise HTTPException(410, detail="O arquivo deste documento não está mais no armazenamento.")
    nome = documento.nome_arquivo
    return Response(
        content=conteudo,
        media_type=documento.content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nome)}"},
    )


@router.delete("/documentos/{documento_id}", status_code=204)
def excluir(documento_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    documento = _obter_documento(db, usuario, documento_id)
    caminho = documento.caminho_storage
    db.delete(documento)
    db.commit()
    arquivos.apagar_arquivos([caminho])
    return Response(status_code=204)
