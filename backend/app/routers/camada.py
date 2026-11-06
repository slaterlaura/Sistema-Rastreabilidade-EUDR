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


_SQL_VERSAO = text(
    """
    SELECT max(v.id) AS versao, max(v.carregada_em) AS atualizada_em,
           coalesce(array_agg(DISTINCT v.bioma ORDER BY v.bioma) FILTER (WHERE v.id IS NOT NULL), '{}') AS biomas
    FROM camada_versao v
    WHERE EXISTS (SELECT 1 FROM camada_prodes p WHERE p.versao_id = v.id)
    """
)


@router.get("/versao")
def versao_atual(response: Response, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    """Identifica a carga mais recente. O mapa põe esse número na URL dos recortes, então uma carga
    nova muda a URL e o navegador não reaproveita a camada antiga do cache."""
    linha = db.execute(_SQL_VERSAO).one()
    imoveis = db.execute(text("SELECT max(versao_id) FROM imovel")).scalar()
    response.headers["Cache-Control"] = "no-store"
    return {
        "versao": linha.versao,
        "atualizada_em": linha.atualizada_em,
        "biomas": list(linha.biomas),
        "imoveis_versao": imoveis,
    }


def _ler_bbox(bbox: str, area_maxima: float = AREA_MAXIMA_GRAUS2) -> tuple[float, float, float, float]:
    try:
        oeste, sul, leste, norte = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(400, detail="bbox deve ser 'oeste,sul,leste,norte' em graus.")
    if not (-180 <= oeste < leste <= 180 and -90 <= sul < norte <= 90):
        raise HTTPException(400, detail="bbox fora dos limites de longitude/latitude.")
    if (leste - oeste) * (norte - sul) > area_maxima:
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
    # A camada só muda numa nova carga, e o frontend põe a versão (?v=) na URL: o navegador pode
    # reaproveitar a resposta (cada chamada é uma execução) sem risco de mostrar camada velha.
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


# Mapa de calor: nível 0 cobre o Brasil inteiro numa resposta; nível 1 só um estado/região por vez.
AREA_MAXIMA_CALOR = {0: 3000.0, 1: 150.0}
LIMITE_PONTOS_CALOR = 40000

_SQL_CALOR = text(
    """
    SELECT lat, lon, area_ha FROM prodes_calor
    WHERE nivel = :nivel AND lat BETWEEN :sul AND :norte AND lon BETWEEN :oeste AND :leste
    ORDER BY area_ha DESC
    LIMIT :limite
    """
)


@router.get("/prodes/calor")
def calor(
    response: Response,
    nivel: int = Query(..., ge=0, le=1, description="0 = células de 0,25° (Brasil/estado); 1 = 0,05° (região)"),
    bbox: str = Query(..., description="oeste,sul,leste,norte (graus, EPSG:4326)"),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    """Desmatamento pós-corte pré-agregado, para o mapa de calor com o mapa afastado.

    Pontos compactos [lat, lon, hectares]; `max` é o percentil 95 dos hectares no recorte, para a
    escala de cor não ser dominada por poucos pontos enormes.
    """
    oeste, sul, leste, norte = _ler_bbox(bbox, AREA_MAXIMA_CALOR[nivel])
    linhas = db.execute(
        _SQL_CALOR,
        {"nivel": nivel, "oeste": oeste, "sul": sul, "leste": leste, "norte": norte, "limite": LIMITE_PONTOS_CALOR + 1},
    ).all()
    truncado = len(linhas) > LIMITE_PONTOS_CALOR
    linhas = linhas[:LIMITE_PONTOS_CALOR]
    areas = sorted(l.area_ha for l in linhas)
    p95 = areas[min(len(areas) - 1, int(len(areas) * 0.95))] if areas else 0.0
    response.headers["Cache-Control"] = "private, max-age=3600"
    return {
        "nivel": nivel,
        "truncado": truncado,
        "max": round(p95, 1),
        "pontos": [[round(l.lat, 4), round(l.lon, 4), round(l.area_ha, 1)] for l in linhas],
    }
