"""Utilitários comuns às cargas de camadas de referência (PRODES, imóveis do CAR).

Leem o que os órgãos distribuem (.zip, .shp, .gpkg, GeoJSON) direto, sem conversão prévia.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyogrio
import shapely
from shapely.ops import unary_union

# Os arquivos oficiais não são consistentes: o PRODES Cerrado traz "MINAS GERAIS", a Mata Atlântica "MG",
# o Pampa mistura os dois. Filtros por UF aceitam todas as formas.
UFS = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
    "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará",
    "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
    "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins",
}


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def formas_da_uf(sigla: str) -> list[str]:
    """Todas as grafias com que a UF aparece nos arquivos oficiais."""
    nome = UFS[sigla]
    formas = {sigla, sigla.lower(), nome, nome.upper(), sem_acento(nome), sem_acento(nome).upper()}
    return sorted(formas)


def sigla_valida(uf: str) -> str:
    sigla = uf.upper()
    if sigla not in UFS:
        raise SystemExit(f"--uf deve ser a sigla de um estado (ex.: MG); recebi '{uf}'.")
    return sigla


def lista_sql(valores) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in valores)


def primeiro_campo(campos: list[str], candidatos: tuple[str, ...]) -> str | None:
    """Primeiro nome de coluna que existe no arquivo, sem diferenciar maiúsculas."""
    por_minuscula = {c.lower(): c for c in campos}
    for candidato in candidatos:
        if candidato.lower() in por_minuscula:
            return por_minuscula[candidato.lower()]
    return None


def poligonos(geom):
    """Repara a geometria e devolve só a parte poligonal (ou None)."""
    if geom is None or geom.is_empty:
        return None
    geom = shapely.make_valid(geom)
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    if geom.geom_type == "GeometryCollection":
        partes = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        return unary_union(partes) if partes else None
    return None


def reparar(geometrias: np.ndarray) -> np.ndarray:
    """Versão vetorizada de poligonos(): só as que não ficam poligonais passam pelo caminho lento."""
    validas = shapely.make_valid(geometrias)
    tipos = shapely.get_type_id(validas)
    lentas = ~np.isin(tipos, (3, 6))  # 3 = Polygon, 6 = MultiPolygon
    if lentas.any():
        validas[lentas] = [poligonos(g) for g in geometrias[lentas]]
    validas[shapely.is_empty(validas)] = None
    return validas


def escolher_camada(caminho: Path, camada: str | None) -> str | None:
    camadas = [nome for nome, _ in pyogrio.list_layers(caminho)]
    if camada:
        if camada not in camadas:
            raise SystemExit(f"Camada '{camada}' não existe em {caminho.name}. Camadas: {camadas}")
        return camada
    if len(camadas) > 1:
        raise SystemExit(f"{caminho.name} tem {len(camadas)} camadas; escolha uma com --camada: {camadas}")
    return camadas[0] if camadas else None


def abrir(caminho: Path, camada: str | None) -> tuple[str | None, dict]:
    """Escolhe a camada e lê os metadados (colunas, tipos, CRS) sem ler as feições."""
    try:
        camada = escolher_camada(caminho, camada)
        return camada, pyogrio.read_info(caminho, layer=camada)
    except SystemExit:
        raise
    except Exception as exc:  # arquivo corrompido, formato desconhecido etc.
        raise SystemExit(f"Não consegui abrir {caminho}: {exc}")


def para_wgs84(gdf: gpd.GeoDataFrame, crs_origem: str | None) -> gpd.GeoDataFrame:
    """Converte para EPSG:4326. Arquivo sem CRS (shapefile sem .prj) só com --crs-origem explícito."""
    if gdf.crs is None:
        if not crs_origem:
            raise SystemExit(
                "O arquivo não informa o sistema de coordenadas (shapefile sem .prj?). "
                "Informe --crs-origem, por exemplo EPSG:4674 (SIRGAS 2000, o dos órgãos brasileiros)."
            )
        gdf = gdf.set_crs(crs_origem)
    return gdf.to_crs(4326)


def salvar_geojson(gdf: gpd.GeoDataFrame, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        destino.unlink()  # o driver GeoJSON não sobrescreve
    gdf.to_file(destino, driver="GeoJSON", COORDINATE_PRECISION=7)


# Mapa de calor: tamanho das células de cada nível, em graus (nível 0 ≈ 28 km, nível 1 ≈ 5,5 km).
NIVEIS_CALOR = {0: 0.25, 1: 0.05}

_SQL_CALOR = """
INSERT INTO prodes_calor (nivel, lat, lon, area_ha, n)
SELECT nivel,
       sum(y * a) / sum(a),            -- centro da célula ponderado pela área desmatada
       sum(x * a) / sum(a),
       sum(a),
       count(*)
FROM (
    SELECT x, y, a,
           unnest(:niveis) AS nivel,
           unnest(:tamanhos) AS t
    FROM (
        SELECT ST_X(c) AS x, ST_Y(c) AS y, a
        FROM (
            SELECT ST_Centroid(geom) AS c,
                   COALESCE(area_km * 100, ST_Area(geom::geography) / 10000) AS a   -- hectares
            FROM camada_prodes
            WHERE ano > :corte
        ) p
        WHERE a > 0
    ) q
) r
GROUP BY nivel, floor(x / t), floor(y / t)
"""


def atualizar_calor(con, ano_corte: int) -> dict[int, int]:
    """Recalcula prodes_calor a partir de camada_prodes, tudo dentro do banco.

    `con` é uma conexão SQLAlchemy já em transação. Devolve quantos pontos ficaram em cada nível.
    """
    from sqlalchemy import text

    con.execute(text("DELETE FROM prodes_calor"))
    con.execute(
        text(_SQL_CALOR),
        {"niveis": list(NIVEIS_CALOR), "tamanhos": list(NIVEIS_CALOR.values()), "corte": ano_corte},
    )
    linhas = con.execute(text("SELECT nivel, count(*) FROM prodes_calor GROUP BY nivel ORDER BY nivel")).all()
    return {int(nivel): int(total) for nivel, total in linhas}
