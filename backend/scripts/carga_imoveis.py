#!/usr/bin/env python3
"""
Carrega a base de imóveis rurais do CAR (SICAR) em public.imovel: camada comum a todos os usuários.

Lê direto o que o SICAR distribui (.zip, .shp, .gpkg) e também GeoJSON. Não é preciso converter.

A carga é um "upsert" pelo código do CAR (cod_imovel):
  - carregar outro município ou estado SOMA à base;
  - recarregar um arquivo ATUALIZA os imóveis que já existiam;
  - nada é apagado.

Colunas reconhecidas (maiúsculas ou minúsculas, nomes do SICAR antigo e novo):
  cod_imovel; num_area; municipio/nom_munici; ind_status/situacao; des_condic/condicao_i; cod_estado/uf.
Sem coluna de UF, a UF sai do próprio código do CAR ("SP-3500105-..." → SP).

Uso:
  python scripts/carga_imoveis.py --arquivo ../data/raw/AREA_IMOVEL_SP.zip
  python scripts/carga_imoveis.py --arquivo ../data/raw/AREA_IMOVEL.zip --uf MG
  python scripts/carga_imoveis.py --arquivo ../data/raw/AREA_IMOVEL.zip --somente-converter ../data/raw/imoveis.geojson
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
from psycopg2.extras import execute_values  # noqa: E402

from scripts.comum_carga import (  # noqa: E402
    abrir,
    formas_da_uf,
    lista_sql,
    para_wgs84,
    primeiro_campo,
    reparar,
    salvar_geojson,
    sigla_valida,
)

CAMPOS = {
    "cod_imovel": ("cod_imovel", "codigo_car", "car"),
    "area_ha": ("num_area", "area_ha", "area"),
    "municipio": ("municipio", "nom_munici", "nom_municipio"),
    "situacao": ("ind_status", "situacao", "status"),
    "condicao": ("des_condic", "condicao_i", "condicao"),
    "uf": ("cod_estado", "uf", "estado", "sigla_uf"),
}
LOTE = 5000


@dataclass
class Resumo:
    lidas: int = 0
    duplicadas: int = 0
    descartadas_geometria: int = 0
    camada: str = ""
    crs_origem: str = ""
    filtro_uf: str | None = None
    colunas: dict[str, str | None] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)


def _texto(serie: pd.Series, limite: int) -> pd.Series:
    return serie.astype("string").str.strip().str.slice(0, limite).replace({"": pd.NA})


def ler_imoveis(
    caminho: Path, *, uf: str | None = None, crs_origem: str | None = None, camada: str | None = None
) -> tuple[gpd.GeoDataFrame, Resumo]:
    """Lê os imóveis em EPSG:4326, com geometria reparada e colunas padronizadas."""
    resumo = Resumo()
    camada, info = abrir(caminho, camada)
    resumo.camada = camada or ""
    campos = list(info["fields"])
    colunas = {destino: primeiro_campo(campos, candidatos) for destino, candidatos in CAMPOS.items()}
    resumo.colunas = colunas
    if colunas["cod_imovel"] is None:
        raise SystemExit(f"Não achei a coluna do código do CAR (cod_imovel). Colunas: {campos}")

    where = None
    if uf:
        resumo.filtro_uf = sigla_valida(uf)
        if colunas["uf"]:
            where = f"\"{colunas['uf']}\" IN ({lista_sql(formas_da_uf(resumo.filtro_uf))})"
        else:  # filtra pelo prefixo do próprio código ("MG-...")
            where = f"\"{colunas['cod_imovel']}\" LIKE '{resumo.filtro_uf}-%'"

    gdf = gpd.read_file(caminho, layer=camada, where=where)
    resumo.lidas = len(gdf)
    resumo.crs_origem = gdf.crs.to_string() if gdf.crs is not None else (crs_origem or "")
    gdf = para_wgs84(gdf, crs_origem)

    cod = _texto(gdf[colunas["cod_imovel"]], 80)
    if colunas["uf"]:
        uf_col = gdf[colunas["uf"]].astype("string").str.strip().str.upper().str.slice(0, 2)
    else:
        uf_col = cod.str.slice(0, 2).str.upper()
    saida = gpd.GeoDataFrame(
        {
            "cod_imovel": cod,
            "municipio": _texto(gdf[colunas["municipio"]], 120) if colunas["municipio"] else pd.NA,
            "uf": uf_col,
            "area_ha": pd.to_numeric(gdf[colunas["area_ha"]], errors="coerce") if colunas["area_ha"] else pd.NA,
            "situacao": _texto(gdf[colunas["situacao"]], 20) if colunas["situacao"] else pd.NA,
            "condicao": _texto(gdf[colunas["condicao"]], 255) if colunas["condicao"] else pd.NA,
        },
        geometry=reparar(gdf.geometry.to_numpy()),
        crs=4326,
    )

    sem_codigo = saida["cod_imovel"].isna()
    if sem_codigo.any():
        resumo.avisos.append(f"{int(sem_codigo.sum())} feições sem código do CAR foram descartadas.")
    saida = saida[~sem_codigo]
    resumo.descartadas_geometria = int(saida.geometry.isna().sum())
    saida = saida[saida.geometry.notna()]

    # O mesmo imóvel duas vezes no arquivo quebraria o upsert: fica a última ocorrência.
    duplicadas = saida["cod_imovel"].duplicated(keep="last")
    resumo.duplicadas = int(duplicadas.sum())
    saida = saida[~duplicadas].reset_index(drop=True)
    return saida, resumo


def _valor(v):
    return None if v is None or (not isinstance(v, str) and pd.isna(v)) else v


def carregar(gdf: gpd.GeoDataFrame, *, origem: str, uf: str | None, arquivo: str) -> tuple[int, int, int]:
    """Upsert numa transação só. Devolve (id da versão, inseridos, atualizados)."""
    from app.database import engine

    linhas = [
        (
            r.cod_imovel, _valor(r.municipio), _valor(r.uf),
            None if _valor(r.area_ha) is None else float(r.area_ha),
            _valor(r.situacao), _valor(r.condicao), r.geometry.wkb_hex,
        )
        for r in gdf.itertuples(index=False)
    ]
    conexao = engine.raw_connection()
    try:
        with conexao.cursor() as cur:
            cur.execute(
                "INSERT INTO imovel_versao (origem, uf, arquivo, n_feicoes) VALUES (%s, %s, %s, %s) RETURNING id",
                (origem, uf, arquivo, len(linhas)),
            )
            versao_id = cur.fetchone()[0]
            cur.execute(
                "CREATE TEMP TABLE _imovel_carga (cod_imovel text, municipio text, uf text, area_ha numeric, "
                "situacao text, condicao text, wkb text) ON COMMIT DROP"
            )
            execute_values(cur, "INSERT INTO _imovel_carga VALUES %s", linhas, page_size=LOTE)
            cur.execute(
                """
                INSERT INTO imovel (cod_imovel, municipio, uf, area_ha, situacao, condicao, versao_id, geom)
                SELECT cod_imovel, municipio, uf, area_ha, situacao, condicao, %s,
                       ST_SetSRID(ST_GeomFromWKB(decode(wkb, 'hex')), 4326)
                FROM _imovel_carga
                ON CONFLICT (cod_imovel) DO UPDATE SET
                    municipio = EXCLUDED.municipio, uf = EXCLUDED.uf, area_ha = EXCLUDED.area_ha,
                    situacao = EXCLUDED.situacao, condicao = EXCLUDED.condicao,
                    versao_id = EXCLUDED.versao_id, geom = EXCLUDED.geom, atualizado_em = now()
                RETURNING (xmax = 0) AS inserido
                """,
                (versao_id,),
            )
            resultado = [r[0] for r in cur.fetchall()]
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
    inseridos = sum(resultado)
    return versao_id, inseridos, len(resultado) - inseridos


def executar(argv: list[str] | None = None) -> int | None:
    """Devolve o id da imovel_versao criada, ou None quando só converte."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arquivo", required=True, type=Path, help=".zip, .shp, .gpkg ou GeoJSON do SICAR")
    p.add_argument("--uf", help="carrega só esta UF (sigla); sem ela, carrega o arquivo inteiro")
    p.add_argument("--camada", help="camada a ler quando o arquivo tem mais de uma")
    p.add_argument("--crs-origem", help="sistema de coordenadas quando o arquivo não informa (ex.: EPSG:4674)")
    p.add_argument("--origem", default="SICAR")
    p.add_argument("--somente-converter", type=Path, metavar="SAIDA.geojson", help="grava o GeoJSON e não toca no banco")
    args = p.parse_args(argv)

    if not args.arquivo.exists():
        raise SystemExit(f"Arquivo não encontrado: {args.arquivo}")

    gdf, r = ler_imoveis(args.arquivo, uf=args.uf, crs_origem=args.crs_origem, camada=args.camada)
    if r.camada:
        print(f"Camada: {r.camada}")
    print(f"Coordenadas de origem: {r.crs_origem} (convertidas para EPSG:4326)")
    print("Colunas usadas: " + ", ".join(f"{k}={v}" for k, v in r.colunas.items() if v))
    if r.filtro_uf:
        print(f"Filtro de UF: {r.filtro_uf}")
    print(f"{len(gdf)} imóveis; por UF: {gdf['uf'].value_counts().to_dict()}")
    if r.duplicadas:
        print(f"Aviso: {r.duplicadas} códigos repetidos no arquivo; ficou a última ocorrência de cada.")
    if r.descartadas_geometria:
        print(f"Aviso: {r.descartadas_geometria} imóveis sem polígono válido foram descartados.")
    for aviso in r.avisos:
        print(f"Aviso: {aviso}")
    if gdf.empty:
        raise SystemExit("Nenhum imóvel sobrou depois dos filtros. Confira --uf e o arquivo.")

    if args.somente_converter:
        salvar_geojson(gdf, args.somente_converter)
        print(f"OK: {len(gdf)} imóveis gravados em {args.somente_converter} (banco não alterado).")
        return None

    versao_id, inseridos, atualizados = carregar(
        gdf, origem=args.origem, uf=r.filtro_uf, arquivo=args.arquivo.name
    )
    print(f"OK: versão {versao_id}; {inseridos} imóveis novos, {atualizados} atualizados.")
    return versao_id


def main() -> None:
    executar()


if __name__ == "__main__":
    main()
