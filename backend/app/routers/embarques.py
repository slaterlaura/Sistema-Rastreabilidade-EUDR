import json
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth import usuario_atual
from app.database import get_db
from app.models import Dossie, Embarque, Fazenda, Parcela, Usuario
from app.schemas import EmbarqueIn, EmbarqueOut, ParcelaOut, ParcelasIn
from app.services import arquivos
from app.services.dossie import montar_geojson, montar_pdf, montar_retrato

router = APIRouter(prefix="/embarques", tags=["embarques"])


def _obter(db: Session, usuario: Usuario, embarque_id: int, *, travar: bool = False) -> Embarque:
    consulta = (
        select(Embarque)
        .options(selectinload(Embarque.parcelas).selectinload(Parcela.fazenda))
        .where(Embarque.id == embarque_id, Embarque.usuario_id == usuario.id)
    )
    if travar:
        consulta = consulta.with_for_update(of=Embarque)
    embarque = db.scalar(consulta)
    if embarque is None:
        raise HTTPException(404, detail="Embarque não encontrado.")
    return embarque


def _exigir_rascunho(embarque: Embarque) -> None:
    if embarque.status != "rascunho":
        raise HTTPException(
            409, detail=f"O embarque {embarque.identificacao} já foi fechado e não pode mais ser alterado."
        )


def _saida(db: Session, embarque: Embarque) -> EmbarqueOut:
    parcelas = [
        ParcelaOut(
            id=p.id,
            fazenda_id=p.fazenda_id,
            fazenda_nome=p.fazenda.nome,
            fazenda_status=p.fazenda.status,
            quantidade_kg=p.quantidade_kg,
            observacao=p.observacao,
        )
        for p in sorted(embarque.parcelas, key=lambda p: p.id)
    ]
    return EmbarqueOut(
        id=embarque.id,
        identificacao=embarque.identificacao,
        data_embarque=embarque.data_embarque,
        destino=embarque.destino,
        status=embarque.status,
        fechado_em=embarque.fechado_em,
        criado_em=embarque.criado_em,
        parcelas=parcelas,
        total_kg=sum((p.quantidade_kg for p in parcelas), Decimal(0)),
        dossie_id=db.scalar(select(Dossie.id).where(Dossie.embarque_id == embarque.id)),
    )


def validar_fazendas_aptas(fazendas: list[Fazenda]) -> None:
    """R2: o bloqueio é do servidor. Nomeia as fazendas recusadas."""
    recusadas = [f for f in fazendas if f.status != "apta"]
    if recusadas:
        detalhes = ", ".join(f"{f.nome} (id {f.id}, {f.status})" for f in recusadas)
        raise HTTPException(
            400,
            detail=f"Fazendas que não estão aptas não podem compor o embarque: {detalhes}. "
            "Remova-as da composição ou regularize a área.",
        )


@router.get("", response_model=list[EmbarqueOut])
def listar(db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    embarques = db.scalars(
        select(Embarque)
        .options(selectinload(Embarque.parcelas).selectinload(Parcela.fazenda))
        .where(Embarque.usuario_id == usuario.id)
        .order_by(Embarque.id.desc())
    ).all()
    return [_saida(db, e) for e in embarques]


@router.post("", response_model=EmbarqueOut, status_code=201)
def criar(dados: EmbarqueIn, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    embarque = Embarque(**dados.model_dump(), usuario_id=usuario.id, status="rascunho")
    db.add(embarque)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, detail="Já existe um embarque com esta identificação na sua conta.")
    return _saida(db, _obter(db, usuario, embarque.id))


@router.get("/{embarque_id}", response_model=EmbarqueOut)
def detalhar(embarque_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    return _saida(db, _obter(db, usuario, embarque_id))


@router.put("/{embarque_id}", response_model=EmbarqueOut)
def atualizar(
    embarque_id: int, dados: EmbarqueIn, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)
):
    embarque = _obter(db, usuario, embarque_id)
    _exigir_rascunho(embarque)
    for campo, valor in dados.model_dump().items():
        setattr(embarque, campo, valor)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, detail="Já existe um embarque com esta identificação na sua conta.")
    return _saida(db, _obter(db, usuario, embarque_id))


@router.delete("/{embarque_id}", status_code=204)
def excluir(embarque_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    embarque = _obter(db, usuario, embarque_id)
    _exigir_rascunho(embarque)
    db.delete(embarque)
    db.commit()
    return Response(status_code=204)


@router.put("/{embarque_id}/parcelas", response_model=EmbarqueOut)
def definir_parcelas(
    embarque_id: int,
    dados: ParcelasIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    """Substitui a composição do rascunho. Cada parcela é uma quantidade de uma única fazenda."""
    embarque = _obter(db, usuario, embarque_id, travar=True)
    _exigir_rascunho(embarque)

    ids = [p.fazenda_id for p in dados.parcelas]
    if len(ids) != len(set(ids)):
        raise HTTPException(400, detail="Há fazendas repetidas na composição. Some as quantidades em uma só parcela.")

    fazendas = {
        f.id: f
        for f in db.scalars(select(Fazenda).where(Fazenda.id.in_(ids), Fazenda.usuario_id == usuario.id))
    }
    ausentes = sorted(set(ids) - set(fazendas))
    if ausentes:
        raise HTTPException(404, detail=f"Fazendas não encontradas: {ausentes}.")
    validar_fazendas_aptas(list(fazendas.values()))

    embarque.parcelas.clear()
    db.flush()
    for p in dados.parcelas:
        embarque.parcelas.append(
            Parcela(fazenda_id=p.fazenda_id, quantidade_kg=p.quantidade_kg, observacao=p.observacao)
        )
    db.commit()
    return _saida(db, _obter(db, usuario, embarque_id))


@router.post("/{embarque_id}/fechar", response_model=EmbarqueOut)
def fechar(embarque_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    """Congela os dados (R3), gera GeoJSON + PDF e torna o embarque imutável."""
    embarque = _obter(db, usuario, embarque_id, travar=True)
    _exigir_rascunho(embarque)
    if not embarque.parcelas:
        raise HTTPException(400, detail="Inclua ao menos uma parcela antes de fechar o embarque.")

    # R2 de novo: o status pode ter mudado depois da composição (ex.: reverificação com PRODES novo)
    validar_fazendas_aptas([p.fazenda for p in embarque.parcelas])

    retrato = montar_retrato(db, embarque, usuario)
    base = f"dossies/{usuario.id}/{embarque.id}"
    caminho_geojson, caminho_pdf = f"{base}/dossie.geojson", f"{base}/dossie.pdf"
    try:
        arquivos.salvar(caminho_geojson, json.dumps(montar_geojson(retrato), ensure_ascii=False).encode("utf-8"))
        arquivos.salvar(caminho_pdf, montar_pdf(retrato))
        db.add(
            Dossie(
                embarque_id=embarque.id,
                retrato=retrato,
                caminho_geojson=caminho_geojson,
                caminho_pdf=caminho_pdf,
            )
        )
        embarque.status = "fechado"
        embarque.fechado_em = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        arquivos.apagar_arquivos([caminho_geojson, caminho_pdf])
        raise
    return _saida(db, _obter(db, usuario, embarque_id))
