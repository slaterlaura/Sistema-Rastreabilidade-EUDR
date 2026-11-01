"""Imóveis do CAR: camada de referência comum a todos os usuários (não filtra por usuario_id).

O exportador vê os imóveis no mapa e "adota" um como fazenda; status, fornecedor e documentos
ficam na fazenda dele, não no imóvel.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import usuario_atual
from app.database import get_db
from app.models import Usuario

router = APIRouter(prefix="/imoveis", tags=["imoveis"])

# Imóveis são muito mais densos que o desmatamento: recorte menor que o da camada PRODES.
AREA_MAXIMA_GRAUS2 = 0.5
LIMITE_FEICOES = 3000

_SQL_RECORTE = text(
    """
    SELECT cod_imovel, municipio, uf, area_ha, situacao,
           ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, :tol), 6) AS geojson
    FROM imovel
    WHERE geom && ST_MakeEnvelope(:oeste, :sul, :leste, :norte, 4326)
    ORDER BY area_ha DESC NULLS LAST
    LIMIT :limite
    """
)

_SQL_UM = text(
    """
    SELECT cod_imovel, municipio, uf, area_ha, situacao, condicao, ST_AsGeoJSON(geom, 9) AS geojson
    FROM imovel WHERE cod_imovel = :cod
    """
)


def _num(valor):
    return None if valor is None else float(valor)


def _ler_bbox(bbox: str) -> tuple[float, float, float, float]:
    try:
        oeste, sul, leste, norte = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(400, detail="bbox deve ser 'oeste,sul,leste,norte' em graus.")
    if not (-180 <= oeste < leste <= 180 and -90 <= sul < norte <= 90):
        raise HTTPException(400, detail="bbox fora dos limites de longitude/latitude.")
    if (leste - oeste) * (norte - sul) > AREA_MAXIMA_GRAUS2:
        raise HTTPException(400, detail="Área do mapa grande demais para os imóveis do CAR. Aproxime o mapa.")
    return oeste, sul, leste, norte


@router.get("")
def recorte(
    response: Response,
    bbox: str = Query(..., description="oeste,sul,leste,norte (graus, EPSG:4326)"),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    """Imóveis do recorte visível do mapa, com geometria simplificada."""
    oeste, sul, leste, norte = _ler_bbox(bbox)
    linhas = db.execute(
        _SQL_RECORTE,
        {"oeste": oeste, "sul": sul, "leste": leste, "norte": norte,
         "tol": max((leste - oeste) / 4000, 0.000005), "limite": LIMITE_FEICOES + 1},
    ).all()
    # A base só muda numa nova carga, e o frontend põe a versão (?v=) na URL: pode ficar em cache.
    response.headers["Cache-Control"] = "private, max-age=3600"
    return {
        "type": "FeatureCollection",
        "truncado": len(linhas) > LIMITE_FEICOES,
        "features": [
            {
                "type": "Feature",
                "geometry": json.loads(l.geojson),
                "properties": {
                    "cod_imovel": l.cod_imovel, "municipio": l.municipio, "uf": l.uf,
                    "area_ha": _num(l.area_ha), "situacao": l.situacao,
                },
            }
            for l in linhas[:LIMITE_FEICOES]
        ],
    }


@router.get("/{cod_imovel}")
def detalhar(cod_imovel: str, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    """Geometria completa e dados do imóvel, para cadastrá-lo como fazenda."""
    linha = db.execute(_SQL_UM, {"cod": cod_imovel}).first()
    if linha is None:
        raise HTTPException(404, detail="Imóvel não encontrado na base do CAR.")
    return {
        "cod_imovel": linha.cod_imovel, "municipio": linha.municipio, "uf": linha.uf,
        "area_ha": _num(linha.area_ha), "situacao": linha.situacao, "condicao": linha.condicao,
        "geometry": json.loads(linha.geojson),
    }
