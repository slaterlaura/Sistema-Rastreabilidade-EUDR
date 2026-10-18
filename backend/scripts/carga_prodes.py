#!/usr/bin/env python3
"""
Carrega a camada de supressão do PRODES em public.camada_prodes.

Cada carga cria uma linha em camada_versao (a fazenda registra qual versão a verificou).
Por padrão, remove as feições de cargas anteriores do mesmo bioma/UF.

Uso:
  python backend/scripts/carga_prodes.py \
      --arquivo data/processed/MataAtlantica_desmatamento_SP.json \
      --bioma "Mata Atlantica" --uf SP

Aceita GeoJSON ou shapefile. O campo de ano é detectado entre: year, ano, ANO, YEAR.
Valores como "2021_2022" viram o ano final (2022).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
from shapely import make_valid  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import engine  # noqa: E402

CAMPOS_ANO = ("year", "ano", "ANO", "YEAR")


def _ano_final(valor) -> int | None:
    """2021 -> 2021; '2021_2022' -> 2022; 'd2025' -> 2025."""
    if pd.isna(valor):
        return None
    anos = re.findall(r"(?:19|20)\d{2}", str(valor))
    return int(anos[-1]) if anos else None


def _poligonos(geom):
    """Repara a geometria e devolve só a parte poligonal (ou None)."""
    if geom is None or geom.is_empty:
        return None
    geom = make_valid(geom)
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    if geom.geom_type == "GeometryCollection":
        partes = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        if not partes:
            return None
        from shapely.ops import unary_union

        return unary_union(partes)
    return None


def ler_camada(caminho: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(caminho)
    if gdf.crs is None:
        print("Aviso: arquivo sem CRS; assumindo EPSG:4326.")
        gdf = gdf.set_crs(4326)
    else:
        gdf = gdf.to_crs(4326)

    campo = next((c for c in CAMPOS_ANO if c in gdf.columns), None)
    if campo is None:
        raise SystemExit(f"Nenhum campo de ano encontrado. Colunas: {list(gdf.columns)}")

    bruto = gdf[campo]
    gdf["ano"] = bruto.map(_ano_final)
    invalidos = int(gdf["ano"].isna().sum())
    if invalidos:
        raise SystemExit(
            f"{invalidos} feições com ano ilegível no campo '{campo}'. "
            f"Valores distintos: {sorted(map(str, bruto.unique()))[:20]}"
        )

    gdf["geometry"] = gdf.geometry.map(_poligonos)
    descartadas = int(gdf.geometry.isna().sum())
    gdf = gdf[gdf.geometry.notna()].copy()
    if descartadas:
        print(f"Aviso: {descartadas} feições sem polígono válido foram descartadas.")

    saida = gpd.GeoDataFrame(
        {
            "ano": gdf["ano"].astype(int),
            "class_name": gdf["class_name"] if "class_name" in gdf.columns else None,
            "area_km": gdf["area_km"] if "area_km" in gdf.columns else None,
        },
        geometry=gdf.geometry,
        crs=4326,
    ).rename_geometry("geom")
    return saida


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arquivo", required=True, type=Path)
    p.add_argument("--bioma", required=True)
    p.add_argument("--uf", help="UF do recorte (ex.: SP)")
    p.add_argument("--origem", default="PRODES")
    p.add_argument("--manter-anteriores", action="store_true", help="não apaga cargas antigas do mesmo bioma/UF")
    args = p.parse_args()

    if not args.arquivo.exists():
        raise SystemExit(f"Arquivo não encontrado: {args.arquivo}")

    gdf = ler_camada(args.arquivo)
    anos = gdf["ano"].value_counts().sort_index()
    print(f"{len(gdf)} feições; anos: {dict(anos)}")
    if gdf["ano"].max() <= settings.ano_corte:
        raise SystemExit(
            f"Nenhuma feição posterior a {settings.ano_corte}: toda fazenda sairia apta. Carga abortada."
        )

    with engine.begin() as con:
        versao_id = con.execute(
            text(
                "INSERT INTO camada_versao (origem, bioma, uf, arquivo, n_feicoes) "
                "VALUES (:o, :b, :u, :a, :n) RETURNING id"
            ),
            {"o": args.origem, "b": args.bioma, "u": args.uf, "a": args.arquivo.name, "n": len(gdf)},
        ).scalar_one()

        gdf.insert(0, "versao_id", versao_id)
        gdf.to_postgis("camada_prodes", con, if_exists="append", index=False)

        if not args.manter_anteriores:
            apagadas = con.execute(
                text(
                    "DELETE FROM camada_prodes WHERE versao_id IN ("
                    "  SELECT id FROM camada_versao WHERE id <> :v AND bioma = :b "
                    "  AND uf IS NOT DISTINCT FROM :u)"
                ),
                {"v": versao_id, "b": args.bioma, "u": args.uf},
            ).rowcount
            if apagadas:
                print(f"{apagadas} feições de cargas anteriores removidas.")

        con.execute(text("ANALYZE camada_prodes"))

    print(f"OK: versão {versao_id} da camada carregada em camada_prodes.")


if __name__ == "__main__":
    main()
