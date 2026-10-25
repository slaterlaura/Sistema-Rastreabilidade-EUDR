from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import usuario_atual
from app.database import get_db
from app.models import Fazenda, Fornecedor, Usuario
from app.schemas import FornecedorIn, FornecedorOut, FornecedorUpdate
from app.services.arquivos import apagar_arquivos, caminhos_documentos

router = APIRouter(prefix="/fornecedores", tags=["fornecedores"])


def _tipo_pessoa(documento: str) -> str:
    return "PF" if len(documento) == 11 else "PJ"


def obter_fornecedor(db: Session, usuario: Usuario, fornecedor_id: int) -> Fornecedor:
    """R6: recurso de outro usuário é indistinguível de recurso inexistente (404)."""
    fornecedor = db.scalar(
        select(Fornecedor).where(Fornecedor.id == fornecedor_id, Fornecedor.usuario_id == usuario.id)
    )
    if fornecedor is None:
        raise HTTPException(404, detail="Fornecedor não encontrado.")
    return fornecedor


def _saida(db: Session, fornecedor: Fornecedor) -> FornecedorOut:
    total = db.scalar(select(func.count()).select_from(Fazenda).where(Fazenda.fornecedor_id == fornecedor.id))
    saida = FornecedorOut.model_validate(fornecedor)
    saida.total_fazendas = total or 0
    return saida


def _conflito_documento() -> HTTPException:
    return HTTPException(409, detail="Já existe um fornecedor com este CPF/CNPJ na sua conta.")


@router.get("", response_model=list[FornecedorOut])
def listar(db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    fornecedores = db.scalars(
        select(Fornecedor).where(Fornecedor.usuario_id == usuario.id).order_by(Fornecedor.nome)
    ).all()
    totais = dict(
        db.execute(
            select(Fazenda.fornecedor_id, func.count())
            .where(Fazenda.usuario_id == usuario.id)
            .group_by(Fazenda.fornecedor_id)
        ).all()
    )
    saidas = []
    for f in fornecedores:
        s = FornecedorOut.model_validate(f)
        s.total_fazendas = totais.get(f.id, 0)
        saidas.append(s)
    return saidas


@router.post("", response_model=FornecedorOut, status_code=201)
def criar(dados: FornecedorIn, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    fornecedor = Fornecedor(
        **dados.model_dump(), usuario_id=usuario.id, tipo_pessoa=_tipo_pessoa(dados.documento)
    )
    db.add(fornecedor)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _conflito_documento()
    return _saida(db, fornecedor)


@router.get("/{fornecedor_id}", response_model=FornecedorOut)
def detalhar(fornecedor_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    return _saida(db, obter_fornecedor(db, usuario, fornecedor_id))


@router.put("/{fornecedor_id}", response_model=FornecedorOut)
def atualizar(
    fornecedor_id: int,
    dados: FornecedorUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    fornecedor = obter_fornecedor(db, usuario, fornecedor_id)
    campos = dados.model_dump(exclude_unset=True)
    if not campos:
        raise HTTPException(400, detail="Nenhum campo para atualizar.")
    for campo, valor in campos.items():
        setattr(fornecedor, campo, valor)
    if "documento" in campos and campos["documento"]:
        fornecedor.tipo_pessoa = _tipo_pessoa(campos["documento"])
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _conflito_documento()
    return _saida(db, fornecedor)


@router.delete("/{fornecedor_id}", status_code=204)
def excluir(fornecedor_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    fornecedor = obter_fornecedor(db, usuario, fornecedor_id)
    caminhos = caminhos_documentos(db, fornecedor_id=fornecedor.id)
    db.delete(fornecedor)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, detail="Este fornecedor tem fazendas cadastradas. Exclua ou transfira as fazendas antes."
        )
    apagar_arquivos(caminhos)
    return Response(status_code=204)
