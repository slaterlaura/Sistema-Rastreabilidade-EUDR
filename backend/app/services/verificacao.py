"""Checagem espacial contra a camada PRODES (R1, R4, R5)."""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import exists, func, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CamadaProdes, CamadaVersao, Fazenda

# O cast ::geography é obrigatório: sem ele ST_Area devolve graus², que não significam nada.
_SQL_AREA = text(
    """
    SELECT COALESCE(SUM(ST_Area(ST_Intersection(f.geom, d.geom)::geography)), 0)
    FROM fazenda f
    JOIN camada_prodes d ON ST_Intersects(f.geom, d.geom)
    WHERE f.id = :id AND d.ano > :corte
    """
)
_SQL_PONTO = text(
    """
    SELECT EXISTS (
        SELECT 1 FROM fazenda f
        JOIN camada_prodes d ON ST_Intersects(f.geom, d.geom)
        WHERE f.id = :id AND d.ano > :corte
    )
    """
)


def verificar_fazenda(db: Session, fazenda: Fazenda) -> Fazenda:
    """Calcula status e área sobreposta. Não faz commit: roda na mesma transação do salvamento."""
    corte = settings.ano_corte

    # Camada vazia faria toda fazenda sair "apta" em silêncio; é melhor recusar.
    if not db.scalar(select(exists().where(CamadaProdes.ano > corte))):
        raise HTTPException(
            status_code=503,
            detail="A camada PRODES não está carregada. Rode backend/scripts/carga_prodes.py antes de cadastrar fazendas.",
        )

    db.flush()  # a geometria precisa estar no banco para a consulta
    tipo = db.scalar(select(func.ST_GeometryType(Fazenda.geom)).where(Fazenda.id == fazenda.id))

    if tipo == "ST_Point":
        # R4/R5: ponto não tem área; o critério é binário e a tolerância não se aplica.
        cai_dentro = db.scalar(_SQL_PONTO, {"id": fazenda.id, "corte": corte})
        area_m2 = Decimal(0)
        bloqueada = bool(cai_dentro)
    else:
        area_m2 = Decimal(str(db.scalar(_SQL_AREA, {"id": fazenda.id, "corte": corte}))).quantize(Decimal("0.01"))
        bloqueada = area_m2 >= Decimal(str(settings.tolerancia_m2))

    fazenda.status = "bloqueada" if bloqueada else "apta"
    fazenda.area_sobreposta_m2 = area_m2
    fazenda.verificada_em = datetime.now(timezone.utc)
    fazenda.camada_versao_id = db.scalar(select(func.max(CamadaVersao.id)))
    db.flush()
    return fazenda
