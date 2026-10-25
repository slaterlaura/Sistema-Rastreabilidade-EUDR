#!/usr/bin/env python3
"""
Carrega a camada de supressão do PRODES em public.camada_prodes.

Não é preciso converter para GeoJSON: o script lê direto o que o TerraBrasilis distribui
(.shp, .zip com o shapefile dentro, .gpkg) e também GeoJSON.

Por padrão ele carrega só o que importa para a EUDR:
  - a UF pedida (--uf), quando o arquivo tem coluna de UF (state, uf, estado);
  - os anos posteriores à data de corte (ano > 2020).
O filtro é aplicado já na leitura, então o bioma inteiro não precisa caber na memória.

Cada carga cria uma linha em camada_versao (a fazenda registra qual versão a verificou)
e, por padrão, remove as feições de cargas anteriores do mesmo bioma/UF.

Uso:
  # carregar no banco
  python scripts/carga_prodes.py --arquivo ../data/raw/yearly_deforestation.zip --bioma Cerrado --uf MG

  # só converter para GeoJSON (mesmos filtros), sem tocar no banco
  python scripts/carga_prodes.py --arquivo ../data/raw/yearly_deforestation.zip --uf MG \
      --somente-converter ../data/raw/prodes_cerrado_mg.geojson

O campo de ano é detectado entre: year, ano, ANO, YEAR.
Valores como "2021_2022" ou "d2025" viram o ano final (2022, 2025).
Arquivo sem sistema de coordenadas (shapefile sem .prj) é recusado; informe --crs-origem.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
import pyogrio  # noqa: E402
from shapely import make_valid  # noqa: E402
from shapely.ops import unary_union  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402

CAMPOS_ANO = ("year", "ano", "ANO", "YEAR")
CAMPOS_UF = ("state", "uf", "estado", "STATE", "UF", "ESTADO")
LOTE_INSERCAO = 5000


@dataclass
class Resumo:
    lidas: int = 0
    descartadas_geometria: int = 0
    crs_origem: str = ""
    campo_ano: str = ""
    campo_uf: str | None = None
    filtro_uf: str | None = None
    filtro_ano_na_leitura: bool = False
    avisos: list[str] = field(default_factory=list)


def _ano_final(valor) -> int | None:
    """2021 -> 2021; '2021_2022' -> 2022; 'd2025' -> 2025."""
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return None
    anos = re.findall(r"(?:19|20)\d{2}", str(valor).split(".")[0])
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
        return unary_union(partes) if partes else None
    return None


def ler_camada(
    caminho: Path,
    *,
    uf: str | None = None,
    todos_os_anos: bool = False,
    crs_origem: str | None = None,
) -> tuple[gpd.GeoDataFrame, Resumo]:
    """Lê o arquivo já filtrado por UF e ano, em EPSG:4326, com geometrias reparadas."""
    resumo = Resumo()
    try:
        info = pyogrio.read_info(caminho)
    except Exception as exc:  # arquivo corrompido, zip com várias camadas etc.
        raise SystemExit(f"Não consegui abrir {caminho}: {exc}")

    campos = list(info["fields"])
    tipos = dict(zip(campos, info["dtypes"]))

    campo_ano = next((c for c in CAMPOS_ANO if c in campos), None)
    if campo_ano is None:
        raise SystemExit(f"Nenhum campo de ano encontrado ({', '.join(CAMPOS_ANO)}). Colunas: {campos}")
    resumo.campo_ano = campo_ano

    clausulas: list[str] = []
    if uf:
        if not re.fullmatch(r"[A-Za-z]{2}", uf):
            raise SystemExit("--uf deve ter duas letras (ex.: MG).")
        resumo.campo_uf = next((c for c in CAMPOS_UF if c in campos), None)
        if resumo.campo_uf:
            resumo.filtro_uf = uf.upper()
            clausulas.append(f"\"{resumo.campo_uf}\" = '{resumo.filtro_uf}'")
        else:
            resumo.avisos.append(f"O arquivo não tem coluna de UF ({', '.join(CAMPOS_UF)}): carreguei todas as feições.")

    # Ano numérico filtra já na leitura; ano em texto ("2021_2022") é filtrado depois, em memória.
    if not todos_os_anos and str(tipos[campo_ano])[:1] in ("i", "u", "f"):
        clausulas.append(f"\"{campo_ano}\" > {settings.ano_corte}")
        resumo.filtro_ano_na_leitura = True

    gdf = gpd.read_file(caminho, where=" AND ".join(clausulas) or None)
    resumo.lidas = len(gdf)

    if gdf.crs is None:
        if not crs_origem:
            raise SystemExit(
                "O arquivo não informa o sistema de coordenadas (shapefile sem .prj?). "
                "Informe --crs-origem, por exemplo EPSG:4674 (SIRGAS 2000, o do TerraBrasilis)."
            )
        gdf = gdf.set_crs(crs_origem)
    resumo.crs_origem = gdf.crs.to_string()
    gdf = gdf.to_crs(4326)

    bruto = gdf[campo_ano]
    gdf["ano"] = bruto.map(_ano_final)
    invalidos = int(gdf["ano"].isna().sum())
    if invalidos:
        raise SystemExit(
            f"{invalidos} feições com ano ilegível no campo '{campo_ano}'. "
            f"Valores distintos: {sorted(map(str, bruto.unique()))[:20]}"
        )
    if not todos_os_anos:
        gdf = gdf[gdf["ano"] > settings.ano_corte]

    gdf = gdf.set_geometry(gdf.geometry.map(_poligonos))
    resumo.descartadas_geometria = int(gdf.geometry.isna().sum())
    gdf = gdf[gdf.geometry.notna()]

    saida = gpd.GeoDataFrame(
        {
            "ano": gdf["ano"].astype(int).to_numpy(),
            "class_name": gdf["class_name"].to_numpy() if "class_name" in gdf.columns else None,
            "area_km": gdf["area_km"].to_numpy() if "area_km" in gdf.columns else None,
        },
        geometry=gdf.geometry.to_numpy(),
        crs=4326,
    ).rename_geometry("geom")
    return saida, resumo


def salvar_geojson(gdf: gpd.GeoDataFrame, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        destino.unlink()  # o driver GeoJSON não sobrescreve
    gdf.to_file(destino, driver="GeoJSON", COORDINATE_PRECISION=7)


def carregar(gdf: gpd.GeoDataFrame, *, origem: str, bioma: str, uf: str | None, arquivo: str, manter_anteriores: bool) -> int:
    """Grava a camada no banco numa transação só; devolve o id da nova versão."""
    from app.database import engine

    with engine.begin() as con:
        versao_id = con.execute(
            text(
                "INSERT INTO camada_versao (origem, bioma, uf, arquivo, n_feicoes) "
                "VALUES (:o, :b, :u, :a, :n) RETURNING id"
            ),
            {"o": origem, "b": bioma, "u": uf, "a": arquivo, "n": len(gdf)},
        ).scalar_one()

        lote = gdf.copy()
        lote.insert(0, "versao_id", versao_id)
        lote.to_postgis("camada_prodes", con, if_exists="append", index=False, chunksize=LOTE_INSERCAO)

        if not manter_anteriores:
            apagadas = con.execute(
                text(
                    "DELETE FROM camada_prodes WHERE versao_id IN ("
                    "  SELECT id FROM camada_versao WHERE id <> :v AND bioma = :b "
                    "  AND uf IS NOT DISTINCT FROM :u)"
                ),
                {"v": versao_id, "b": bioma, "u": uf},
            ).rowcount
            if apagadas:
                print(f"{apagadas} feições de cargas anteriores de {bioma}/{uf or '—'} removidas.")

        con.execute(text("ANALYZE camada_prodes"))
    return versao_id


def _imprimir_resumo(gdf: gpd.GeoDataFrame, r: Resumo) -> None:
    anos = {int(a): int(n) for a, n in gdf["ano"].value_counts().sort_index().items()}
    print(f"Coordenadas de origem: {r.crs_origem} (convertidas para EPSG:4326)")
    if r.filtro_uf:
        print(f"Filtro de UF: {r.campo_uf} = {r.filtro_uf}")
    print(f"{len(gdf)} feições após os filtros; por ano: {anos}")
    if r.descartadas_geometria:
        print(f"Aviso: {r.descartadas_geometria} feições sem polígono válido foram descartadas.")
    for aviso in r.avisos:
        print(f"Aviso: {aviso}")


def executar(argv: list[str] | None = None) -> int | None:
    """Devolve o id da camada_versao criada, ou None quando só converte."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arquivo", required=True, type=Path, help=".shp, .zip, .gpkg ou GeoJSON")
    p.add_argument("--bioma", help="rótulo da versão (ex.: Cerrado); obrigatório para carregar no banco")
    p.add_argument("--uf", help="UF do recorte (ex.: MG): filtra o arquivo e rotula a versão")
    p.add_argument("--origem", default="PRODES")
    p.add_argument("--crs-origem", help="sistema de coordenadas quando o arquivo não informa (ex.: EPSG:4674)")
    p.add_argument("--todos-os-anos", action="store_true", help=f"não descarta anos até {settings.ano_corte}")
    p.add_argument("--manter-anteriores", action="store_true", help="não apaga cargas antigas do mesmo bioma/UF")
    p.add_argument("--somente-converter", type=Path, metavar="SAIDA.geojson", help="grava o GeoJSON filtrado e não toca no banco")
    p.add_argument("--salvar-geojson", type=Path, metavar="SAIDA.geojson", help="além de carregar, grava o que foi carregado")
    args = p.parse_args(argv)

    if not args.arquivo.exists():
        raise SystemExit(f"Arquivo não encontrado: {args.arquivo}")
    if not args.somente_converter and not args.bioma:
        raise SystemExit("Informe --bioma para carregar no banco (ou use --somente-converter).")

    gdf, resumo = ler_camada(args.arquivo, uf=args.uf, todos_os_anos=args.todos_os_anos, crs_origem=args.crs_origem)
    _imprimir_resumo(gdf, resumo)
    if gdf.empty:
        raise SystemExit("Nenhuma feição sobrou depois dos filtros. Confira --uf e o arquivo.")

    if args.somente_converter:
        salvar_geojson(gdf, args.somente_converter)
        print(f"OK: {len(gdf)} feições gravadas em {args.somente_converter} (banco não alterado).")
        return None

    if gdf["ano"].max() <= settings.ano_corte:  # só acontece com --todos-os-anos
        raise SystemExit(
            f"Nenhuma feição posterior a {settings.ano_corte}: toda fazenda sairia apta. Carga abortada."
        )

    versao_id = carregar(
        gdf,
        origem=args.origem,
        bioma=args.bioma,
        uf=args.uf.upper() if args.uf else None,
        arquivo=args.arquivo.name,
        manter_anteriores=args.manter_anteriores,
    )
    if args.salvar_geojson:
        salvar_geojson(gdf, args.salvar_geojson)
        print(f"Cópia em GeoJSON: {args.salvar_geojson}")
    print(f"OK: versão {versao_id} da camada carregada em camada_prodes.")
    print("Próximo passo: no app, Fazendas → Reprocessar camada (reverifica as fazendas existentes).")
    return versao_id


def main() -> None:
    executar()


if __name__ == "__main__":
    main()
