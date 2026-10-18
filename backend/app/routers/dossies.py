import re
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import usuario_atual
from app.database import get_db
from app.models import Dossie, Embarque, Usuario
from app.schemas import DossieOut
from app.services import arquivos

router = APIRouter(prefix="/dossies", tags=["dossies"])


def _obter(db: Session, usuario: Usuario, dossie_id: int) -> Dossie:
    dossie = db.scalar(
        select(Dossie).join(Embarque, Embarque.id == Dossie.embarque_id)
        .where(Dossie.id == dossie_id, Embarque.usuario_id == usuario.id)
    )
    if dossie is None:
        raise HTTPException(404, detail="Dossiê não encontrado.")
    return dossie


def _saida(dossie: Dossie, *, com_retrato: bool) -> DossieOut:
    r = dossie.retrato
    return DossieOut(
        id=dossie.id,
        embarque_id=dossie.embarque_id,
        embarque_identificacao=r["embarque"]["identificacao"],
        destino=r["embarque"]["destino"],
        data_embarque=r["embarque"]["data_embarque"],
        n_parcelas=len(r["parcelas"]),
        total_kg=Decimal(str(r["total_kg"])),
        gerado_em=dossie.gerado_em,
        retrato=r if com_retrato else None,
    )


def _arquivo(dossie: Dossie, caminho: str | None, media_type: str, extensao: str) -> Response:
    try:
        if not caminho:
            raise FileNotFoundError
        conteudo = arquivos.ler(caminho)
    except FileNotFoundError:
        raise HTTPException(410, detail="O arquivo deste dossiê não está mais no armazenamento.")
    nome = re.sub(r"[^A-Za-z0-9._-]+", "_", dossie.retrato["embarque"]["identificacao"])
    return Response(
        content=conteudo,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="dossie-{nome}.{extensao}"'},
    )


@router.get("", response_model=list[DossieOut])
def listar(db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    """Visão de auditoria: todos os dossiês da conta, sem o retrato completo."""
    dossies = db.scalars(
        select(Dossie).join(Embarque, Embarque.id == Dossie.embarque_id)
        .where(Embarque.usuario_id == usuario.id).order_by(Dossie.id.desc())
    ).all()
    return [_saida(d, com_retrato=False) for d in dossies]


@router.get("/{dossie_id}", response_model=DossieOut)
def detalhar(dossie_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    return _saida(_obter(db, usuario, dossie_id), com_retrato=True)


@router.get("/{dossie_id}/geojson")
def baixar_geojson(dossie_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    dossie = _obter(db, usuario, dossie_id)
    return _arquivo(dossie, dossie.caminho_geojson, "application/geo+json", "geojson")


@router.get("/{dossie_id}/pdf")
def baixar_pdf(dossie_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    dossie = _obter(db, usuario, dossie_id)
    return _arquivo(dossie, dossie.caminho_pdf, "application/pdf", "pdf")
