"""Validação e normalização de geometrias recebidas (GeoJSON, sempre SRID 4326)."""

import json
from decimal import Decimal

from fastapi import HTTPException
from geoalchemy2.shape import from_shape
from shapely.geometry import shape
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

AREA_MAXIMA_HA = 100_000  # acima disso, quase certamente é GeoJSON colado por engano
AREA_MAXIMA_PONTO_HA = 4  # R4: ponto só é aceito para parcelas de até 4 ha
TIPOS_ACEITOS = {"Polygon", "MultiPolygon", "Point"}

_SQL = text(
    """
    WITH entrada AS (
        SELECT ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326) AS g0
    ), reparada AS (
        SELECT CASE
                 WHEN ST_IsValid(g0) THEN g0
                 WHEN GeometryType(g0) IN ('POLYGON', 'MULTIPOLYGON')
                      THEN ST_CollectionExtract(ST_MakeValid(g0), 3)
                 ELSE ST_MakeValid(g0)
               END AS g
        FROM entrada
    )
    SELECT ST_AsGeoJSON(g, 9) AS geojson,
           ST_IsEmpty(g)      AS vazia,
           ST_Area(g::geography) / 10000.0 AS area_ha
    FROM reparada
    """
)


def _erro(detalhe: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detalhe)


def validar_geometria(db: Session, entrada: dict, area_declarada_ha: Decimal | float | None):
    """Devolve (geometria pronta para gravar, área calculada em ha).

    Aceita Geometry ou Feature. Levanta HTTPException 400 em português.
    """
    geometria = entrada.get("geometry") if entrada.get("type") == "Feature" else entrada
    if not isinstance(geometria, dict) or geometria.get("type") not in TIPOS_ACEITOS:
        raise _erro("Geometria inválida. Envie um Polígono, MultiPolígono ou Ponto em GeoJSON.")

    try:
        linha = db.execute(_SQL, {"g": json.dumps(geometria)}).one()
    except SQLAlchemyError:
        db.rollback()
        raise _erro(
            "Não foi possível ler a geometria. Confira o GeoJSON: coordenadas em [longitude, latitude] (graus) "
            "e anéis de polígono fechados."
        )

    if linha.vazia:
        raise _erro("Geometria vazia ou impossível de corrigir (autointerseção). Redesenhe o contorno.")

    eh_ponto = geometria["type"] == "Point"
    area_ha = Decimal(str(linha.area_ha)) if linha.area_ha is not None else Decimal(0)

    if eh_ponto:
        if area_declarada_ha is None:
            raise _erro("Para localizar a fazenda por ponto, informe a área declarada (até 4 ha).")
        if Decimal(str(area_declarada_ha)) > AREA_MAXIMA_PONTO_HA:
            raise _erro(
                f"Ponto só é aceito para áreas de até {AREA_MAXIMA_PONTO_HA} ha. "
                "Acima disso, envie o polígono."
            )
    else:
        if area_ha <= 0:
            raise _erro("O polígono tem área zero. Confira as coordenadas.")
        if area_ha > AREA_MAXIMA_HA:
            raise _erro(
                f"Área de {area_ha:.0f} ha excede o limite de {AREA_MAXIMA_HA} ha. "
                "Provavelmente o GeoJSON errado foi colado."
            )

    return from_shape(shape(json.loads(linha.geojson)), srid=4326), area_ha
