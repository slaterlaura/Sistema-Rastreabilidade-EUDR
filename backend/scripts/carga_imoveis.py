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
import time
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
import pyogrio  # noqa: E402
import shapely  # noqa: E402
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


def _preparar(caminho: Path, uf: str | None, camada: str | None) -> tuple[str | None, dict, str | None, Resumo]:
    """Descobre a camada, as colunas do SICAR e o filtro de UF, sem ler as feições."""
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
    return camada, colunas, where, resumo


def _padronizar(gdf: gpd.GeoDataFrame, colunas: dict, resumo: Resumo) -> gpd.GeoDataFrame:
    """Colunas padronizadas, geometria reparada, sem código vazio e sem código repetido (fica o último)."""
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
    sem_codigo = int(saida["cod_imovel"].isna().sum())
    if sem_codigo:
        resumo.avisos.append(f"{sem_codigo} feições sem código do CAR foram descartadas.")
    saida = saida[saida["cod_imovel"].notna()]
    resumo.descartadas_geometria += int(saida.geometry.isna().sum())
    saida = saida[saida.geometry.notna()]
    # O mesmo imóvel duas vezes no mesmo lote quebraria o upsert: fica a última ocorrência.
    duplicadas = saida["cod_imovel"].duplicated(keep="last")
    resumo.duplicadas += int(duplicadas.sum())
    return saida[~duplicadas].reset_index(drop=True)


def ler_imoveis(
    caminho: Path, *, uf: str | None = None, crs_origem: str | None = None, camada: str | None = None
) -> tuple[gpd.GeoDataFrame, Resumo]:
    """Lê o arquivo INTEIRO na memória. Para arquivos grandes, use ler_em_lotes()."""
    camada, colunas, where, resumo = _preparar(caminho, uf, camada)
    gdf = gpd.read_file(caminho, layer=camada, where=where)
    resumo.lidas = len(gdf)
    resumo.crs_origem = gdf.crs.to_string() if gdf.crs is not None else (crs_origem or "")
    return _padronizar(para_wgs84(gdf, crs_origem), colunas, resumo), resumo


def ler_em_lotes(
    caminho: Path, *, uf: str | None = None, crs_origem: str | None = None, camada: str | None = None, lote: int = 20000
) -> tuple[Iterator[gpd.GeoDataFrame], Resumo]:
    """Lê o arquivo aos poucos (lotes de `lote` feições), sem nunca carregá-lo inteiro na memória.

    Necessário para bases estaduais grandes (ex.: Minas Gerais, ~2,7 GB em GeoJSON).
    """
    camada, colunas, where, resumo = _preparar(caminho, uf, camada)

    def gerar() -> Iterator[gpd.GeoDataFrame]:
        with pyogrio.open_arrow(
            caminho, layer=camada, where=where, batch_size=lote, use_pyarrow=True
        ) as (meta, leitor):
            crs = meta.get("crs")
            resumo.crs_origem = crs or (crs_origem or "")
            coluna_geom = meta.get("geometry_name") or "wkb_geometry"
            for bloco in leitor:
                if bloco.num_rows == 0:
                    continue
                atributos = bloco.drop_columns([coluna_geom]).to_pandas()
                geometrias = shapely.from_wkb(bloco.column(coluna_geom).to_numpy(zero_copy_only=False))
                gdf = gpd.GeoDataFrame(atributos, geometry=geometrias, crs=crs)
                resumo.lidas += len(gdf)
                yield _padronizar(para_wgs84(gdf, crs_origem), colunas, resumo)

    return gerar(), resumo


def _valor(v):
    return None if v is None or (not isinstance(v, str) and pd.isna(v)) else v


_SQL_UPSERT = """
    INSERT INTO imovel (cod_imovel, municipio, uf, area_ha, situacao, condicao, versao_id, geom)
    SELECT cod_imovel, municipio, uf, area_ha, situacao, condicao, %s,
           ST_SetSRID(ST_GeomFromWKB(decode(wkb, 'hex')), 4326)
    FROM _imovel_carga
    ON CONFLICT (cod_imovel) DO UPDATE SET
        municipio = EXCLUDED.municipio, uf = EXCLUDED.uf, area_ha = EXCLUDED.area_ha,
        situacao = EXCLUDED.situacao, condicao = EXCLUDED.condicao,
        versao_id = EXCLUDED.versao_id, geom = EXCLUDED.geom, atualizado_em = now()
    RETURNING (xmax = 0) AS inserido
"""


def carregar_em_lotes(
    lotes: Iterable[gpd.GeoDataFrame], *, origem: str, uf: str | None, arquivo: str, mostrar: bool = False
) -> tuple[int, int, int, Counter]:
    """Upsert lote a lote, cada um no seu commit (uma queda no meio não perde o que já entrou, e rodar
    de novo não duplica nada). Devolve (id da versão, inseridos, atualizados, imóveis por UF)."""
    from app.database import engine

    conexao = engine.raw_connection()
    inseridos = atualizados = 0
    por_uf: Counter = Counter()
    inicio = time.perf_counter()
    try:
        with conexao.cursor() as cur:
            cur.execute(
                "INSERT INTO imovel_versao (origem, uf, arquivo, n_feicoes) VALUES (%s, %s, %s, 0) RETURNING id",
                (origem, uf, arquivo),
            )
            versao_id = cur.fetchone()[0]
        conexao.commit()

        for numero, gdf in enumerate(lotes, start=1):
            if gdf.empty:
                continue
            linhas = [
                (
                    r.cod_imovel, _valor(r.municipio), _valor(r.uf),
                    None if _valor(r.area_ha) is None else float(r.area_ha),
                    _valor(r.situacao), _valor(r.condicao), r.geometry.wkb_hex,
                )
                for r in gdf.itertuples(index=False)
            ]
            with conexao.cursor() as cur:
                cur.execute(
                    "CREATE TEMP TABLE _imovel_carga (cod_imovel text, municipio text, uf text, area_ha numeric, "
                    "situacao text, condicao text, wkb text) ON COMMIT DROP"
                )
                execute_values(cur, "INSERT INTO _imovel_carga VALUES %s", linhas, page_size=LOTE)
                cur.execute(_SQL_UPSERT, (versao_id,))
                resultado = [r[0] for r in cur.fetchall()]
                cur.execute(
                    "UPDATE imovel_versao SET n_feicoes = n_feicoes + %s WHERE id = %s", (len(resultado), versao_id)
                )
            conexao.commit()
            novos = sum(resultado)
            inseridos += novos
            atualizados += len(resultado) - novos
            por_uf.update(gdf["uf"].dropna())
            if mostrar:
                print(
                    f"  lote {numero}: {len(resultado)} imóveis "
                    f"(total {inseridos + atualizados}, {time.perf_counter() - inicio:.0f} s)",
                    flush=True,
                )
        with conexao.cursor() as cur:
            cur.execute("ANALYZE imovel")
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
    return versao_id, inseridos, atualizados, por_uf


def carregar(gdf: gpd.GeoDataFrame, *, origem: str, uf: str | None, arquivo: str) -> tuple[int, int, int]:
    """Carrega um GeoDataFrame já lido inteiro (usado pelos testes e por arquivos pequenos)."""
    versao_id, inseridos, atualizados, _ = carregar_em_lotes([gdf], origem=origem, uf=uf, arquivo=arquivo)
    return versao_id, inseridos, atualizados


def executar(argv: list[str] | None = None) -> int | None:
    """Devolve o id da imovel_versao criada, ou None quando só converte."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arquivo", required=True, type=Path, help=".zip, .shp, .gpkg ou GeoJSON do SICAR")
    p.add_argument("--uf", help="carrega só esta UF (sigla); sem ela, carrega o arquivo inteiro")
    p.add_argument("--camada", help="camada a ler quando o arquivo tem mais de uma")
    p.add_argument("--crs-origem", help="sistema de coordenadas quando o arquivo não informa (ex.: EPSG:4674)")
    p.add_argument("--origem", default="SICAR")
    p.add_argument("--lote", type=int, default=20000, help="imóveis por lote (memória e commit); padrão 20000")
    p.add_argument("--somente-converter", type=Path, metavar="SAIDA.geojson", help="grava o GeoJSON e não toca no banco")
    args = p.parse_args(argv)

    if not args.arquivo.exists():
        raise SystemExit(f"Arquivo não encontrado: {args.arquivo}")

    if args.somente_converter:  # o GeoJSON de saída precisa ser escrito de uma vez: lê o arquivo inteiro
        gdf, r = ler_imoveis(args.arquivo, uf=args.uf, crs_origem=args.crs_origem, camada=args.camada)
        if gdf.empty:
            raise SystemExit("Nenhum imóvel sobrou depois dos filtros. Confira --uf e o arquivo.")
        salvar_geojson(gdf, args.somente_converter)
        print(f"OK: {len(gdf)} imóveis gravados em {args.somente_converter} (banco não alterado).")
        return None

    lotes, r = ler_em_lotes(
        args.arquivo, uf=args.uf, crs_origem=args.crs_origem, camada=args.camada, lote=args.lote
    )
    if r.camada:
        print(f"Camada: {r.camada}")
    print("Colunas usadas: " + ", ".join(f"{k}={v}" for k, v in r.colunas.items() if v))
    if r.filtro_uf:
        print(f"Filtro de UF: {r.filtro_uf}")
    print(f"Carregando em lotes de {args.lote}…", flush=True)
    versao_id, inseridos, atualizados, por_uf = carregar_em_lotes(
        lotes, origem=args.origem, uf=r.filtro_uf, arquivo=args.arquivo.name, mostrar=True
    )
    print(f"Coordenadas de origem: {r.crs_origem} (convertidas para EPSG:4326)")
    if r.duplicadas:
        print(f"Aviso: {r.duplicadas} códigos repetidos dentro de um mesmo lote; ficou a última ocorrência.")
    if r.descartadas_geometria:
        print(f"Aviso: {r.descartadas_geometria} imóveis sem polígono válido foram descartados.")
    for aviso in r.avisos:
        print(f"Aviso: {aviso}")
    if inseridos + atualizados == 0:
        raise SystemExit("Nenhum imóvel carregado. Confira --uf e o arquivo.")
    print(f"Por UF: {dict(por_uf)}")
    print(f"OK: versão {versao_id}; {inseridos} imóveis novos, {atualizados} atualizados.")
    return versao_id


def main() -> None:
    executar()


if __name__ == "__main__":
    main()
