"""Carga da base de imóveis do CAR (scripts/carga_imoveis.py): upsert por cod_imovel, colunas do SICAR."""

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box
from sqlalchemy import text

from app.database import engine

_spec = importlib.util.spec_from_file_location(
    "carga_imoveis", Path(__file__).resolve().parents[1] / "scripts" / "carga_imoveis.py"
)
carga = importlib.util.module_from_spec(_spec)
sys.modules["carga_imoveis"] = carga  # o @dataclass procura o módulo aqui
_spec.loader.exec_module(carga)


def _shapefile(pasta: Path, nome: str, colunas: dict, crs="EPSG:4674") -> Path:
    n = len(next(iter(colunas.values())))
    gdf = gpd.GeoDataFrame(colunas, geometry=[box(-47 + i * 0.01, -21, -46.995 + i * 0.01, -20.995) for i in range(n)], crs=crs)
    caminho = pasta / f"{nome}.shp"
    gdf.to_file(caminho)
    return caminho


def _sicar_novo(pasta: Path, nome="AREA_IMOVEL", **extra) -> Path:
    """Formato do download atual do SICAR: colunas em maiúsculas, nomes truncados em 10 letras."""
    colunas = {
        "COD_IMOVEL": ["MG-3100104-AAA", "MG-3100104-BBB", "SP-3500105-CCC"],
        "NUM_AREA": [12.5, 300.0, 44.3],
        "COD_ESTADO": ["MG", "MG", "SP"],
        "NOM_MUNICI": ["Abadia dos Dourados", "Abadia dos Dourados", "Adamantina"],
        "SITUACAO": ["AT", "PE", "AT"],
        "CONDICAO_I": ["Aguardando analise", "Aguardando analise", "Analisado"],
    }
    colunas.update(extra)
    return _shapefile(pasta, nome, colunas)


def _imoveis():
    with engine.connect() as con:
        return con.execute(
            text("SELECT cod_imovel, uf, municipio, area_ha, situacao, ST_SRID(geom) AS srid FROM imovel ORDER BY cod_imovel")
        ).all()


def test_sicar_novo_em_maiusculas_carrega_em_wgs84(tmp_path):
    versao = carga.executar(["--arquivo", str(_sicar_novo(tmp_path))])
    linhas = _imoveis()
    assert versao is not None and len(linhas) == 3
    mg = linhas[0]
    assert (mg.cod_imovel, mg.uf, mg.municipio, float(mg.area_ha), mg.situacao, mg.srid) == (
        "MG-3100104-AAA", "MG", "Abadia dos Dourados", 12.5, "AT", 4326,
    )


def test_formato_antigo_em_minusculas_e_uf_tirada_do_codigo(tmp_path):
    shp = _shapefile(tmp_path, "antigo", {
        "cod_imovel": ["SP-3500105-X1", "SP-3500105-X2"],
        "municipio": ["Adamantina", "Adamantina"],
        "num_area": [10.0, 20.0],
        "ind_status": ["AT", "CA"],
        "des_condic": ["Aguardando analise", "Cancelado"],
    })
    carga.executar(["--arquivo", str(shp)])
    assert [(l.cod_imovel, l.uf, l.situacao) for l in _imoveis()] == [("SP-3500105-X1", "SP", "AT"), ("SP-3500105-X2", "SP", "CA")]


def test_recarga_atualiza_sem_duplicar_e_soma_outros(tmp_path):
    carga.executar(["--arquivo", str(_sicar_novo(tmp_path))])
    atualizado = _sicar_novo(tmp_path, "ATUALIZADO", NUM_AREA=[99.0, 300.0, 44.3])
    carga.executar(["--arquivo", str(atualizado)])
    novo = _shapefile(tmp_path, "OUTRO", {"COD_IMOVEL": ["GO-5200050-ZZZ"], "COD_ESTADO": ["GO"]})
    carga.executar(["--arquivo", str(novo)])
    linhas = {l.cod_imovel: l for l in _imoveis()}
    assert len(linhas) == 4 and float(linhas["MG-3100104-AAA"].area_ha) == 99.0
    with engine.connect() as con:
        assert con.execute(text("SELECT count(*) FROM imovel_versao")).scalar_one() == 3


def test_filtro_por_uf_pela_coluna_ou_pelo_codigo(tmp_path):
    gdf, resumo = carga.ler_imoveis(_sicar_novo(tmp_path), uf="mg")
    assert sorted(gdf["cod_imovel"]) == ["MG-3100104-AAA", "MG-3100104-BBB"] and resumo.filtro_uf == "MG"
    sem_uf = _shapefile(tmp_path, "sem_uf", {"cod_imovel": ["SP-1-A", "MG-1-B"]})
    gdf, _ = carga.ler_imoveis(sem_uf, uf="SP")
    assert list(gdf["cod_imovel"]) == ["SP-1-A"]


def test_codigo_repetido_no_arquivo_fica_a_ultima_ocorrencia(tmp_path):
    shp = _shapefile(tmp_path, "rep", {"cod_imovel": ["SP-1-A", "SP-1-A"], "num_area": [1.0, 2.0]})
    gdf, resumo = carga.ler_imoveis(shp)
    assert len(gdf) == 1 and float(gdf["area_ha"].iloc[0]) == 2.0 and resumo.duplicadas == 1


def test_sem_coluna_de_codigo_e_recusado(tmp_path):
    shp = _shapefile(tmp_path, "sem_cod", {"nome": ["x"]})
    with pytest.raises(SystemExit, match="cod_imovel"):
        carga.ler_imoveis(shp)


def test_sem_prj_exige_crs_de_origem(tmp_path):
    shp = _sicar_novo(tmp_path)
    shp.with_suffix(".prj").unlink()
    with pytest.raises(SystemExit, match="--crs-origem"):
        carga.ler_imoveis(shp)
    gdf, _ = carga.ler_imoveis(shp, crs_origem="EPSG:4674")
    assert gdf.crs.to_epsg() == 4326


def test_zip_e_somente_converter(tmp_path):
    shp = _sicar_novo(tmp_path)
    zipado = tmp_path / "AREA_IMOVEL.zip"
    with zipfile.ZipFile(zipado, "w") as z:
        for parte in tmp_path.glob("AREA_IMOVEL.*"):
            if parte.suffix != ".zip":
                z.write(parte, parte.name)
    saida = tmp_path / "saida.geojson"
    assert carga.executar(["--arquivo", str(zipado), "--uf", "SP", "--somente-converter", str(saida)]) is None
    colecao = json.loads(saida.read_text())
    assert [f["properties"]["cod_imovel"] for f in colecao["features"]] == ["SP-3500105-CCC"]
    assert _imoveis() == []
