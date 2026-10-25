import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import usuario_atual
from app.config import settings
from app.database import get_db
from app.models import Usuario

router = APIRouter(prefix="/camada", tags=["camada"])

# Recortes grandes demais trariam o estado inteiro (MBs) numa execução só; o mapa pede para aproximar.
AREA_MAXIMA_GRAUS2 = 4.0
LIMITE_FEICOES = 3000

_SQL = text(
    """
    SELECT d.id, d.ano, d.area_km,
           ST_AsGeoJSON(ST_SimplifyPreserveTopology(d.geom, :tol), 6) AS geojson
    FROM camada_prodes d
    WHERE d.geom && ST_MakeEnvelope(:oeste, :sul, :leste, :norte, 4326)
      AND d.ano > :corte
    ORDER BY d.area_km DESC NULLS LAST
    LIMIT :limite
    """
)


def _ler_bbox(bbox: str) -> tuple[float, float, float, float]:
    try:
        oeste, sul, leste, norte = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(400, detail="bbox deve ser 'oeste,sul,leste,norte' em graus.")
    if not (-180 <= oeste < leste <= 180 and -90 <= sul < norte <= 90):
        raise HTTPException(400, detail="bbox fora dos limites de longitude/latitude.")
    if (leste - oeste) * (norte - sul) > AREA_MAXIMA_GRAUS2:
        raise HTTPException(400, detail="Área do mapa grande demais para a camada de supressão. Aproxime o mapa.")
    return oeste, sul, leste, norte


@router.get("/prodes")
def supressao(
    response: Response,
    bbox: str = Query(..., description="oeste,sul,leste,norte (graus, EPSG:4326)"),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    """Polígonos de supressão posteriores à data de corte, no recorte pedido, para desenhar sob as fazendas."""
    oeste, sul, leste, norte = _ler_bbox(bbox)
    tolerancia = max((leste - oeste) / 2000, 0.00001)  # simplifica conforme o zoom
    linhas = db.execute(
        _SQL,
        {"oeste": oeste, "sul": sul, "leste": leste, "norte": norte,
         "corte": settings.ano_corte, "tol": tolerancia, "limite": LIMITE_FEICOES + 1},
    ).all()
    truncado = len(linhas) > LIMITE_FEICOES
    # A camada só muda numa nova carga: o navegador pode reaproveitar a resposta (cada chamada é uma execução).
    response.headers["Cache-Control"] = "private, max-age=3600"
    return {
        "type": "FeatureCollection",
        "truncado": truncado,
        "features": [
            {
                "type": "Feature",
                "geometry": json.loads(l.geojson),
                "properties": {"id": l.id, "ano": l.ano, "area_km": float(l.area_km) if l.area_km is not None else None},
            }
            for l in linhas[:LIMITE_FEICOES]
        ],
    }
